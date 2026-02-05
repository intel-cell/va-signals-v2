"""
RegInfo.gov PRA submissions ingestor for Authority Layer.

Scrapes Paperwork Reduction Act submissions for VA from:
- https://www.reginfo.gov/public/do/PRASearch

Tracks information collection requests that VA submits to OMB for approval.
"""

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}

# RegInfo PRA Search endpoint
REGINFO_SEARCH_URL = "https://www.reginfo.gov/public/do/PRASearch"

# VA agency codes used in RegInfo
VA_AGENCY_CODES = [
    "2900",  # Department of Veterans Affairs
]


def _compute_hash(content: str) -> str:
    """Compute SHA-256 hash of content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _generate_doc_id(icr_ref: str, omb_control: str) -> str:
    """Generate a stable doc_id from ICR reference or OMB control number."""
    if icr_ref:
        clean_ref = re.sub(r"[^a-zA-Z0-9-]", "", icr_ref)
        return f"pra-{clean_ref.lower()}"
    if omb_control:
        clean_omb = re.sub(r"[^0-9-]", "", omb_control)
        return f"pra-{clean_omb}"
    # Fallback
    return f"pra-{hashlib.sha256(str(datetime.now()).encode()).hexdigest()[:12]}"


def _parse_date(date_str: str) -> Optional[str]:
    """Parse date string to ISO format."""
    if not date_str:
        return None

    date_str = date_str.strip()
    formats = [
        "%m/%d/%Y",       # 01/29/2026
        "%Y-%m-%d",       # 2026-01-29
        "%B %d, %Y",      # January 29, 2026
        "%b %d, %Y",      # Jan 29, 2026
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue

    return None


def _classify_request_type(title: str, status: str = "") -> str:
    """Classify the type of PRA request."""
    text = f"{title} {status}".lower()

    if "new" in text and "collection" in text:
        return "new_collection"
    elif "revision" in text:
        return "revision"
    elif "extension" in text:
        return "extension"
    elif "reinstatement" in text:
        return "reinstatement"
    elif "emergency" in text:
        return "emergency"
    else:
        return "information_collection"


def fetch_va_pra_submissions(
    max_items: int = 50,
    recent_days: int = 90,
) -> list[dict]:
    """
    Fetch VA's PRA submissions from RegInfo.gov.

    Args:
        max_items: Maximum items to fetch
        recent_days: Only fetch submissions from last N days

    Returns:
        List of dicts ready for upsert_authority_doc()
    """
    docs = []

    # Build search parameters for VA
    # The RegInfo search interface uses form parameters
    params = {
        "ession": "",  # Session handling
        "agency": "2900",  # VA agency code
        "actionType": "",  # All action types
        "sortColumn": "receiveDate",  # Sort by received date
        "sortOrder": "DESC",  # Most recent first
    }

    try:
        # RegInfo uses a session-based form, try direct URL with params
        search_url = f"{REGINFO_SEARCH_URL}?{urlencode(params)}"
        resp = requests.get(search_url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"Error fetching RegInfo PRA page: {e}")
        return docs

    soup = BeautifulSoup(resp.text, "html.parser")

    # RegInfo typically shows results in a table
    # Look for table rows with submission data
    tables = soup.select("table")

    for table in tables:
        rows = table.select("tr")

        # Skip header row
        for row in rows[1:]:
            if len(docs) >= max_items:
                break

            cells = row.select("td")
            if len(cells) < 3:
                continue

            try:
                # Extract data from cells - order may vary
                # Typical columns: ICR Ref, OMB Control, Title, Agency, Status, Received
                icr_ref = ""
                omb_control = ""
                title = ""
                status = ""
                received_date = ""

                for i, cell in enumerate(cells):
                    cell_text = cell.get_text(strip=True)

                    # Try to identify column by content pattern
                    if re.match(r"\d{12}", cell_text):
                        icr_ref = cell_text
                    elif re.match(r"\d{4}-\d{4}", cell_text):
                        omb_control = cell_text
                    elif re.match(r"\d{1,2}/\d{1,2}/\d{4}", cell_text):
                        if not received_date:
                            received_date = cell_text
                    elif len(cell_text) > 30:
                        if not title:
                            title = cell_text
                    elif cell_text.lower() in ["pending", "approved", "withdrawn", "active"]:
                        status = cell_text

                # If we didn't find a title, use the longest text
                if not title:
                    texts = [c.get_text(strip=True) for c in cells]
                    title = max(texts, key=len) if texts else "Unknown"

                if not title or len(title) < 5:
                    continue

                # Get link if available
                link = row.select_one("a[href]")
                source_url = REGINFO_SEARCH_URL
                if link:
                    href = link.get("href", "")
                    if href and not href.startswith("http"):
                        source_url = f"https://www.reginfo.gov{href}"
                    elif href:
                        source_url = href

                doc = {
                    "doc_id": _generate_doc_id(icr_ref, omb_control),
                    "authority_source": "omb_oira",
                    "authority_type": _classify_request_type(title, status),
                    "title": title[:500],
                    "published_at": _parse_date(received_date),
                    "source_url": source_url,
                    "body_text": None,
                    "content_hash": _compute_hash(f"{icr_ref}{omb_control}{title}"),
                    "metadata_json": json.dumps({
                        "icr_reference": icr_ref,
                        "omb_control_number": omb_control,
                        "status": status,
                        "agency": "Department of Veterans Affairs",
                    }),
                }
                docs.append(doc)

            except Exception as e:
                print(f"Error parsing row: {e}")
                continue

    # If table parsing didn't work, try alternative link-based extraction
    if not docs:
        docs = _extract_from_links(soup, max_items)

    return docs


def _extract_from_links(soup: BeautifulSoup, max_items: int) -> list[dict]:
    """Alternative extraction method using link patterns."""
    docs = []
    seen = set()

    for link in soup.select("a[href*='ICRView'], a[href*='icrId']"):
        if len(docs) >= max_items:
            break

        href = link.get("href", "")
        text = link.get_text(strip=True)

        if not text or len(text) < 10:
            continue

        if not href.startswith("http"):
            href = f"https://www.reginfo.gov{href}"

        if href in seen:
            continue
        seen.add(href)

        # Extract ICR ID from URL
        icr_match = re.search(r"icrId=(\d+)", href)
        icr_ref = icr_match.group(1) if icr_match else ""

        doc = {
            "doc_id": _generate_doc_id(icr_ref, ""),
            "authority_source": "omb_oira",
            "authority_type": "information_collection",
            "title": text[:500],
            "published_at": None,
            "source_url": href,
            "body_text": None,
            "content_hash": _compute_hash(href),
            "metadata_json": json.dumps({
                "icr_reference": icr_ref,
                "agency": "Department of Veterans Affairs",
            }),
        }
        docs.append(doc)

    return docs


if __name__ == "__main__":
    # Test run
    docs = fetch_va_pra_submissions(max_items=10)
    print(f"Fetched {len(docs)} VA PRA submissions:")
    for doc in docs:
        meta = json.loads(doc["metadata_json"])
        omb = meta.get("omb_control_number", "N/A")
        print(f"  [{omb}] {doc['title'][:60]}...")
