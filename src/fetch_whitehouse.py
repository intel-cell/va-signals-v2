"""
White House document ingestor for Authority Layer.

Scrapes:
- https://www.whitehouse.gov/briefing-room/statements-releases/
- https://www.whitehouse.gov/briefing-room/presidential-actions/

Extracts: bill signings, executive orders, memoranda, proclamations.
"""

import hashlib
import json
import logging
from datetime import UTC, datetime

import requests
from bs4 import BeautifulSoup

from .resilience.circuit_breaker import whitehouse_cb
from .resilience.wiring import circuit_breaker_sync, with_timeout

logger = logging.getLogger(__name__)

# User agent to avoid blocks
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

# Source pages to scrape
WHITEHOUSE_SOURCES = {
    "statements_releases": {
        "url": "https://www.whitehouse.gov/briefing-room/statements-releases/",
        "types": ["bill_signing", "statement", "press_release"],
    },
    "presidential_actions": {
        "url": "https://www.whitehouse.gov/briefing-room/presidential-actions/",
        "types": ["executive_order", "memorandum", "proclamation", "determination"],
    },
}

# Keywords to classify document types
TYPE_KEYWORDS = {
    "executive_order": ["executive order", "e.o."],
    "memorandum": ["memorandum", "presidential memorandum"],
    "proclamation": ["proclamation"],
    "bill_signing": ["signed into law", "bill signing", "signs h.r.", "signs s."],
    "determination": ["presidential determination"],
    "statement": ["statement by", "statement from", "statement of"],
}


def _compute_hash(content: str) -> str:
    """Compute SHA-256 hash of content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _generate_doc_id(url: str) -> str:
    """Generate a stable doc_id from URL."""
    # Extract slug from URL
    slug = url.rstrip("/").split("/")[-1]
    return f"wh-{slug[:60]}"


def _classify_type(title: str, source_key: str) -> str:
    """Classify document type based on title and source."""
    title_lower = title.lower()

    for doc_type, keywords in TYPE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in title_lower:
                return doc_type

    # Default based on source
    if source_key == "presidential_actions":
        return "executive_action"
    return "statement"


def _is_va_relevant(title: str, body: str = "") -> bool:
    """Check if document is potentially VA-relevant."""
    text = f"{title} {body}".lower()
    va_keywords = [
        "veteran",
        "veterans",
        "va ",
        "department of veterans affairs",
        "military",
        "service member",
        "servicemember",
        "armed forces",
        "gi bill",
        "vha",
        "vba",
        "nca",
        "pact act",
        "burn pit",
        "toxic exposure",
        "disability compensation",
        "benefits",
    ]
    return any(kw in text for kw in va_keywords)


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
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.replace(tzinfo=UTC).isoformat()
        except ValueError:
            continue

    return None


@with_timeout(45, name="whitehouse")
@circuit_breaker_sync(whitehouse_cb)
def _fetch_whitehouse_page(url: str) -> requests.Response:
    """Fetch a White House page with resilience protection."""
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp


def _scrape_listing_page(url: str, source_key: str) -> list[dict]:
    """Scrape a White House listing page for document links."""
    docs = []

    try:
        resp = _fetch_whitehouse_page(url)
    except requests.RequestException as e:
        logger.error("Error fetching %s: %s", url, e)
        return docs

    soup = BeautifulSoup(resp.text, "html.parser")

    # Find article/news items - WH site uses various structures
    # Try common patterns
    items = soup.select("article.news-item, .briefing-statement, article, .wp-block-post")

    for item in items:
        try:
            # Find title and link
            title_link = item.select_one("h2 a, h3 a, .news-item__title a, a.wp-block-post-title")
            if not title_link:
                # Try just finding the main link
                title_link = item.select_one("a[href*='/briefing-room/']")
                if not title_link:
                    continue

            title = title_link.get_text(strip=True)
            link = title_link.get("href", "")

            if not title or not link:
                continue

            # Build full URL
            if not link.startswith("http"):
                link = f"https://www.whitehouse.gov{link}"

            # Skip if not a briefing room link
            if "/briefing-room/" not in link:
                continue

            # Find date
            date_elem = item.select_one("time, .date, .news-item__date, .wp-block-post-date")
            date_str = None
            if date_elem:
                date_str = date_elem.get("datetime") or date_elem.get_text(strip=True)

            # Classify type
            doc_type = _classify_type(title, source_key)

            docs.append(
                {
                    "url": link,
                    "title": title,
                    "published_at": _parse_date(date_str),
                    "authority_type": doc_type,
                    "source_key": source_key,
                }
            )

        except Exception:
            continue

    return docs


def _fetch_document_body(url: str) -> tuple[str, str]:
    """Fetch full document body text. Returns (body_text, content_hash)."""
    try:
        resp = _fetch_whitehouse_page(url)
    except requests.RequestException as e:
        logger.error("Error fetching document %s: %s", url, e)
        return "", ""

    soup = BeautifulSoup(resp.text, "html.parser")

    # Find main content area
    content = soup.select_one(
        "article .body-content, "
        ".body-content, "
        "article .entry-content, "
        ".entry-content, "
        "main article, "
        ".page-content"
    )

    if not content:
        content = soup.select_one("main, article")

    body_text = ""
    if content:
        # Remove script/style elements
        for elem in content.select("script, style, nav, header, footer"):
            elem.decompose()
        body_text = content.get_text(separator="\n", strip=True)

    content_hash = _compute_hash(body_text) if body_text else ""
    return body_text[:50000], content_hash  # Limit body size


def fetch_whitehouse_docs(
    fetch_body: bool = True,
    va_filter: bool = True,
    max_per_source: int = 20,
) -> list[dict]:
    """
    Fetch documents from White House briefing room pages.

    Args:
        fetch_body: Whether to fetch full document body text
        va_filter: Whether to filter for VA-relevant documents only
        max_per_source: Maximum items to fetch per source page

    Returns:
        List of dicts ready for upsert_authority_doc()
    """
    all_docs = []
    seen_urls = set()

    for source_key, source in WHITEHOUSE_SOURCES.items():
        docs = _scrape_listing_page(source["url"], source_key)

        for doc in docs[:max_per_source]:
            if doc["url"] in seen_urls:
                continue
            seen_urls.add(doc["url"])

            # Fetch body if requested
            body_text = ""
            content_hash = ""
            if fetch_body:
                body_text, content_hash = _fetch_document_body(doc["url"])

            # VA relevance filter
            if va_filter and not _is_va_relevant(doc["title"], body_text):
                continue

            authority_doc = {
                "doc_id": _generate_doc_id(doc["url"]),
                "authority_source": "whitehouse",
                "authority_type": doc["authority_type"],
                "title": doc["title"],
                "published_at": doc["published_at"],
                "source_url": doc["url"],
                "body_text": body_text,
                "content_hash": content_hash,
                "metadata_json": json.dumps(
                    {
                        "source_key": doc["source_key"],
                    }
                ),
            }
            all_docs.append(authority_doc)

    return all_docs


if __name__ == "__main__":
    # Test run
    docs = fetch_whitehouse_docs(fetch_body=True, va_filter=False, max_per_source=5)
    print(f"Fetched {len(docs)} documents:")
    for doc in docs:
        print(f"  [{doc['authority_type']}] {doc['title'][:60]}...")
