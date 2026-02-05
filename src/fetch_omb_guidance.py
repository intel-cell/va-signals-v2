"""
OMB Guidance document ingestor for Authority Layer.

Scrapes OMB memoranda from:
- https://www.whitehouse.gov/omb/information-regulatory-affairs/memoranda/

Extracts: memo IDs (M-26-01), titles, dates, PDF links.
"""

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Optional

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}

OMB_MEMORANDA_URL = "https://www.whitehouse.gov/omb/information-regulatory-affairs/memoranda/"

# Regex to extract memo ID like M-26-01, M-25-12
MEMO_ID_PATTERN = re.compile(r"M-\d{2}-\d{1,2}")


def _compute_hash(content: str) -> str:
    """Compute SHA-256 hash of content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _generate_doc_id(memo_id: str, url: str) -> str:
    """Generate a stable doc_id."""
    if memo_id:
        return f"omb-{memo_id.lower()}"
    # Fallback to URL hash
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:12]
    return f"omb-{url_hash}"


def _extract_memo_id(title: str, url: str) -> Optional[str]:
    """Extract memo ID from title or URL."""
    # Try title first
    match = MEMO_ID_PATTERN.search(title)
    if match:
        return match.group(0)

    # Try URL
    match = MEMO_ID_PATTERN.search(url)
    if match:
        return match.group(0)

    return None


def _parse_date(date_str: str) -> Optional[str]:
    """Parse date string to ISO format."""
    if not date_str:
        return None

    date_str = date_str.strip()
    formats = [
        "%B %d, %Y",      # January 29, 2026
        "%B %Y",          # January 2026
        "%b %d, %Y",      # Jan 29, 2026
        "%Y-%m-%d",       # 2026-01-29
        "%m/%d/%Y",       # 01/29/2026
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue

    # Try to extract year at minimum
    year_match = re.search(r"20\d{2}", date_str)
    if year_match:
        return f"{year_match.group(0)}-01-01T00:00:00+00:00"

    return None


def _is_va_relevant(title: str) -> bool:
    """Check if memo is potentially VA-relevant based on title."""
    text = title.lower()
    va_keywords = [
        "veteran", "va ", "benefits", "healthcare", "health care",
        "appropriation", "budget", "agency", "federal", "personnel",
        "hiring", "workforce", "regulatory", "rulemaking", "grants",
        "information collection", "pra", "paperwork", "oira",
    ]
    return any(kw in text for kw in va_keywords)


def fetch_omb_guidance_docs(
    va_filter: bool = False,
    max_items: int = 50,
) -> list[dict]:
    """
    Fetch OMB memoranda from the OMB OIRA page.

    Args:
        va_filter: Whether to filter for VA-relevant memos only
        max_items: Maximum items to fetch

    Returns:
        List of dicts ready for upsert_authority_doc()
    """
    docs = []

    try:
        resp = requests.get(OMB_MEMORANDA_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"Error fetching OMB memoranda page: {e}")
        return docs

    soup = BeautifulSoup(resp.text, "html.parser")

    # The memoranda page typically has a table or list of memos
    # Look for links that contain memo references
    seen_urls = set()

    # Try to find memo entries - could be in tables, lists, or article blocks
    for link in soup.select("a[href]"):
        href = link.get("href", "")
        text = link.get_text(strip=True)

        if not href or not text:
            continue

        # Skip navigation links
        if len(text) < 10:
            continue

        # Check if this looks like a memo link (PDF or page with M-XX-XX)
        is_memo = (
            ".pdf" in href.lower() or
            MEMO_ID_PATTERN.search(text) or
            MEMO_ID_PATTERN.search(href) or
            "memorand" in text.lower() or
            "circular" in text.lower()
        )

        if not is_memo:
            continue

        # Build full URL
        if not href.startswith("http"):
            if href.startswith("/"):
                href = f"https://www.whitehouse.gov{href}"
            else:
                continue

        if href in seen_urls:
            continue
        seen_urls.add(href)

        if len(docs) >= max_items:
            break

        memo_id = _extract_memo_id(text, href)

        # Try to find associated date
        parent = link.parent
        date_str = None
        if parent:
            # Look for date in same row/container
            date_elem = parent.select_one("time, .date, td:last-child")
            if date_elem:
                date_str = date_elem.get("datetime") or date_elem.get_text(strip=True)
            else:
                # Try text content for date patterns
                parent_text = parent.get_text()
                date_match = re.search(
                    r"(January|February|March|April|May|June|July|August|"
                    r"September|October|November|December)\s+\d{1,2},?\s+\d{4}",
                    parent_text,
                    re.IGNORECASE
                )
                if date_match:
                    date_str = date_match.group(0)

        # VA relevance filter
        if va_filter and not _is_va_relevant(text):
            continue

        # Determine type based on content
        authority_type = "memorandum"
        text_lower = text.lower()
        if "circular" in text_lower:
            authority_type = "circular"
        elif "bulletin" in text_lower:
            authority_type = "bulletin"
        elif "guidance" in text_lower:
            authority_type = "guidance"

        doc = {
            "doc_id": _generate_doc_id(memo_id, href),
            "authority_source": "omb",
            "authority_type": authority_type,
            "title": text[:500],
            "published_at": _parse_date(date_str),
            "source_url": href,
            "body_text": None,  # PDFs need separate extraction
            "content_hash": _compute_hash(href),  # Use URL as proxy for now
            "metadata_json": json.dumps({
                "memo_id": memo_id,
                "is_pdf": ".pdf" in href.lower(),
            }),
        }
        docs.append(doc)

    return docs


if __name__ == "__main__":
    # Test run
    docs = fetch_omb_guidance_docs(va_filter=False, max_items=10)
    print(f"Fetched {len(docs)} OMB memos:")
    for doc in docs:
        memo_id = json.loads(doc["metadata_json"]).get("memo_id", "N/A")
        print(f"  [{memo_id}] {doc['title'][:60]}...")
