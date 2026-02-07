"""
VA Publications ingestor for Authority Layer.

Scrapes VA official publications from:
- https://www.va.gov/vapubs/

Extracts: Directives, Handbooks, Notices, Circulars.
"""

import hashlib
import json
import re
from datetime import UTC, datetime

import requests
from bs4 import BeautifulSoup

from .resilience.circuit_breaker import va_pubs_cb
from .resilience.wiring import circuit_breaker_sync, with_timeout

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

VA_PUBS_URL = "https://www.va.gov/vapubs/"

# Publication type patterns
PUB_TYPE_PATTERNS = {
    "directive": re.compile(r"directive\s*\d+", re.IGNORECASE),
    "handbook": re.compile(r"handbook\s*\d+", re.IGNORECASE),
    "notice": re.compile(r"notice\s*\d+", re.IGNORECASE),
    "circular": re.compile(r"circular\s*\d+", re.IGNORECASE),
    "mp": re.compile(r"mp-?\d+", re.IGNORECASE),  # Management Publications
}


def _compute_hash(content: str) -> str:
    """Compute SHA-256 hash of content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _generate_doc_id(pub_number: str, url: str) -> str:
    """Generate a stable doc_id."""
    if pub_number:
        clean_num = re.sub(r"[^a-zA-Z0-9-]", "", pub_number)
        return f"va-pub-{clean_num.lower()}"
    # Fallback to URL hash
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:12]
    return f"va-pub-{url_hash}"


def _extract_pub_number(text: str, url: str) -> str | None:
    """Extract publication number from text or URL."""
    # Try various patterns
    patterns = [
        r"(\d+-\d+(?:\.\d+)?)",  # 5021-1.2
        r"(Directive\s+\d+(?:-\d+)?)",  # Directive 5021
        r"(Handbook\s+\d+(?:-\d+)?)",  # Handbook 5021
        r"(MP-\d+)",  # MP-1
        r"(VHA\s*\d+)",  # VHA1401
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)

    # Try URL
    for pattern in patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


def _classify_pub_type(title: str, pub_number: str = "") -> str:
    """Classify publication type."""
    text = f"{title} {pub_number}".lower()

    for pub_type, pattern in PUB_TYPE_PATTERNS.items():
        if pattern.search(text):
            return pub_type

    if "handbook" in text:
        return "handbook"
    elif "directive" in text:
        return "directive"
    elif "notice" in text:
        return "notice"
    elif "policy" in text:
        return "policy"
    else:
        return "publication"


def _parse_date(date_str: str) -> str | None:
    """Parse date string to ISO format."""
    if not date_str:
        return None

    date_str = date_str.strip()
    formats = [
        "%B %d, %Y",  # January 29, 2026
        "%b %d, %Y",  # Jan 29, 2026
        "%Y-%m-%d",  # 2026-01-29
        "%m/%d/%Y",  # 01/29/2026
        "%m/%d/%y",  # 01/29/26
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.replace(tzinfo=UTC).isoformat()
        except ValueError:
            continue

    return None


def _extract_administrations(title: str) -> list[str]:
    """Extract VA administrations mentioned (VHA, VBA, NCA)."""
    admins = []
    text = title.upper()

    if "VHA" in text or "HEALTH" in text:
        admins.append("VHA")
    if "VBA" in text or "BENEFITS" in text:
        admins.append("VBA")
    if "NCA" in text or "CEMETERY" in text or "CEMETERIES" in text:
        admins.append("NCA")

    return admins


def fetch_va_pubs_docs(
    max_items: int = 50,
) -> list[dict]:
    """
    Fetch VA publications from vapubs.

    Args:
        max_items: Maximum items to fetch

    Returns:
        List of dicts ready for upsert_authority_doc()
    """
    docs = []

    @with_timeout(45, name="va_pubs")
    @circuit_breaker_sync(va_pubs_cb)
    def _get_va_pubs_page(url):
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        return resp

    try:
        resp = _get_va_pubs_page(VA_PUBS_URL)
    except requests.RequestException as e:
        print(f"Error fetching VA Publications page: {e}")
        return docs

    soup = BeautifulSoup(resp.text, "html.parser")
    seen_urls = set()

    # The VA pubs site structure varies - look for publication links
    # Could be in tables, lists, or search results
    for link in soup.select("a[href]"):
        href = link.get("href", "")
        text = link.get_text(strip=True)

        if not href or not text:
            continue

        # Skip short/navigation links
        if len(text) < 5:
            continue

        # Check if this looks like a publication link
        is_pub = (
            ".pdf" in href.lower()
            or "directive" in text.lower()
            or "handbook" in text.lower()
            or "notice" in text.lower()
            or any(pattern.search(text) for pattern in PUB_TYPE_PATTERNS.values())
            or any(pattern.search(href) for pattern in PUB_TYPE_PATTERNS.values())
        )

        if not is_pub:
            continue

        # Build full URL
        if not href.startswith("http"):
            if href.startswith("/"):
                href = f"https://www.va.gov{href}"
            else:
                href = f"{VA_PUBS_URL}{href}"

        if href in seen_urls:
            continue
        seen_urls.add(href)

        if len(docs) >= max_items:
            break

        pub_number = _extract_pub_number(text, href)
        pub_type = _classify_pub_type(text, pub_number or "")

        # Try to find associated date
        parent = link.parent
        date_str = None
        if parent:
            # Look for date in adjacent cells or elements
            for sibling in [parent.find_next_sibling(), parent.find_previous_sibling()]:
                if sibling:
                    sib_text = sibling.get_text(strip=True)
                    date_match = re.search(
                        r"(\d{1,2}/\d{1,2}/\d{2,4})|"
                        r"((January|February|March|April|May|June|July|August|"
                        r"September|October|November|December)\s+\d{1,2},?\s+\d{4})",
                        sib_text,
                        re.IGNORECASE,
                    )
                    if date_match:
                        date_str = date_match.group(0)
                        break

        doc = {
            "doc_id": _generate_doc_id(pub_number, href),
            "authority_source": "va",
            "authority_type": pub_type,
            "title": text[:500],
            "published_at": _parse_date(date_str),
            "source_url": href,
            "body_text": None,  # PDFs need separate extraction
            "content_hash": _compute_hash(href),
            "metadata_json": json.dumps(
                {
                    "pub_number": pub_number,
                    "administrations": _extract_administrations(text),
                    "is_pdf": ".pdf" in href.lower(),
                }
            ),
        }
        docs.append(doc)

    return docs


def fetch_va_pubs_search(
    query: str = "directive",
    max_items: int = 20,
) -> list[dict]:
    """
    Search VA publications with a query term.
    Some VA pubs sites have search functionality.
    """
    # The main vapubs page may have a search - try common patterns
    search_urls = [
        f"https://www.va.gov/vapubs/search/?q={query}",
        f"https://www.va.gov/vapubs/?search={query}",
    ]

    all_docs = []
    seen_urls = set()

    for search_url in search_urls:
        try:
            resp = requests.get(search_url, headers=HEADERS, timeout=30)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")

            for link in soup.select("a[href*='.pdf'], a[href*='directive'], a[href*='handbook']"):
                href = link.get("href", "")
                text = link.get_text(strip=True)

                if not href.startswith("http"):
                    href = f"https://www.va.gov{href}"

                if href in seen_urls or not text:
                    continue
                seen_urls.add(href)

                if len(all_docs) >= max_items:
                    break

                pub_number = _extract_pub_number(text, href)
                doc = {
                    "doc_id": _generate_doc_id(pub_number, href),
                    "authority_source": "va",
                    "authority_type": _classify_pub_type(text, pub_number or ""),
                    "title": text[:500],
                    "published_at": None,
                    "source_url": href,
                    "body_text": None,
                    "content_hash": _compute_hash(href),
                    "metadata_json": json.dumps(
                        {
                            "pub_number": pub_number,
                            "search_query": query,
                        }
                    ),
                }
                all_docs.append(doc)

        except requests.RequestException:
            continue

    return all_docs


if __name__ == "__main__":
    # Test run
    docs = fetch_va_pubs_docs(max_items=10)
    print(f"Fetched {len(docs)} VA publications:")
    for doc in docs:
        meta = json.loads(doc["metadata_json"])
        pub_num = meta.get("pub_number", "N/A")
        print(f"  [{doc['authority_type']}] {pub_num}: {doc['title'][:50]}...")
