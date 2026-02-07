"""
Fetch VA-related bills from Congress.gov API.

Targets VA committees:
- House Veterans' Affairs Committee (hsvr00)
- Senate Veterans' Affairs Committee (ssva00)

Usage:
    python -m src.fetch_bills [--congress N] [--limit N] [--dry-run]
"""

import argparse
import json
import logging
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime

import certifi

from . import db
from .resilience.circuit_breaker import congress_api_cb
from .resilience.wiring import circuit_breaker_sync, with_timeout
from .secrets import get_env_or_keychain

logger = logging.getLogger(__name__)

# VA-related committee codes
VA_COMMITTEES = {
    "hsvr00": "House Veterans' Affairs Committee",
    "ssva00": "Senate Veterans' Affairs Committee",
}

BASE_API_URL = "https://api.congress.gov/v3"


def get_api_key() -> str:
    """Get Congress.gov API key from environment or Keychain."""
    return get_env_or_keychain("CONGRESS_API_KEY", "congress-api")


@with_timeout(45, name="congress_api")
@circuit_breaker_sync(congress_api_cb)
def _fetch_json(url: str, api_key: str) -> dict:
    """Fetch JSON from Congress.gov API."""
    sep = "&" if "?" in url else "?"
    full_url = f"{url}{sep}api_key={api_key}&format=json"
    req = urllib.request.Request(
        full_url,
        headers={
            "Accept": "application/json",
            "User-Agent": "VA-Signals/1.0",
        },
    )
    context = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(req, timeout=30, context=context) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _utc_now_iso() -> str:
    """Return current UTC time in ISO format."""
    return datetime.now(UTC).isoformat()


def parse_bill_id(url_or_bill: str) -> tuple[int, str, int]:
    """
    Parse a bill identifier from a URL or bill_id string.

    Args:
        url_or_bill: Either a Congress.gov API URL like
            "https://api.congress.gov/v3/bill/119/hr/1234"
            or a bill_id string like "hr-119-1234"

    Returns:
        Tuple of (congress, bill_type, number)

    Examples:
        >>> parse_bill_id("https://api.congress.gov/v3/bill/119/hr/1234")
        (119, 'hr', 1234)
        >>> parse_bill_id("hr-119-1234")
        (119, 'hr', 1234)
    """
    # Try URL pattern: /bill/{congress}/{type}/{number}
    url_match = re.search(r"/bill/(\d+)/([a-z]+)/(\d+)", url_or_bill.lower())
    if url_match:
        return int(url_match.group(1)), url_match.group(2), int(url_match.group(3))

    # Try bill_id pattern: {type}-{congress}-{number}
    bill_id_match = re.match(r"^([a-z]+)-(\d+)-(\d+)$", url_or_bill.lower())
    if bill_id_match:
        return int(bill_id_match.group(2)), bill_id_match.group(1), int(bill_id_match.group(3))

    raise ValueError(f"Cannot parse bill identifier: {url_or_bill}")


def fetch_committee_bills(committee_code: str, congress: int = 119, limit: int = 250) -> list[dict]:
    """
    Fetch bills referred to a committee.

    Args:
        committee_code: Committee system code (e.g., 'hsvr00', 'ssva00')
        congress: Congress number (default: 119)
        limit: Maximum number of bills to fetch

    Returns:
        List of bill metadata dicts with keys:
        - congress, bill_type, number, title, url
    """
    api_key = get_api_key()

    # Determine chamber from committee code
    chamber = "house" if committee_code.startswith("h") else "senate"

    bills = []
    offset = 0

    while len(bills) < limit:
        url = f"{BASE_API_URL}/committee/{chamber}/{committee_code}/bills?congress={congress}&limit=100&offset={offset}"
        try:
            data = _fetch_json(url, api_key)
        except urllib.error.HTTPError as e:
            logger.error("Error fetching committee bills page %d: %s", offset, e)
            break

        # Handle different API response structures
        batch = data.get("committee-bills", {}).get("bills", [])
        if not batch:
            batch = data.get("bills", [])
        if not batch:
            break

        for b in batch:
            # Extract bill info from the response
            bill_url = b.get("url", "")
            try:
                if bill_url:
                    congress_num, bill_type, number = parse_bill_id(bill_url)
                else:
                    congress_num = b.get("congress", congress)
                    bill_type = b.get("type", "").lower()
                    number = b.get("number")
            except ValueError:
                continue

            if not bill_type or not number:
                continue

            # Filter to requested congress only
            if congress_num != congress:
                continue

            bills.append(
                {
                    "congress": congress_num,
                    "bill_type": bill_type,
                    "number": number,
                    "title": b.get("title", ""),
                    "url": bill_url,
                }
            )

        offset += 100
        if not data.get("pagination", {}).get("next"):
            break

    return bills[:limit]


def fetch_bill_details(congress: int, bill_type: str, number: int) -> dict | None:
    """
    Fetch detailed information for a specific bill.

    Args:
        congress: Congress number (e.g., 119)
        bill_type: Bill type (e.g., 'hr', 's', 'hjres')
        number: Bill number

    Returns:
        Dict with bill details or None if not found:
        - bill_id, congress, bill_type, bill_number, title
        - sponsor_name, sponsor_bioguide_id, sponsor_party, sponsor_state
        - introduced_date, latest_action_date, latest_action_text
        - policy_area, committees, cosponsors_count
    """
    api_key = get_api_key()

    url = f"{BASE_API_URL}/bill/{congress}/{bill_type.lower()}/{number}"
    try:
        data = _fetch_json(url, api_key)
    except urllib.error.HTTPError as e:
        logger.error("Error fetching bill %s-%d: %s", bill_type.upper(), number, e)
        return None

    bill = data.get("bill", {})
    if not bill:
        return None

    # Build bill_id in format: {type}-{congress}-{number}
    bill_id = f"{bill_type.lower()}-{congress}-{number}"

    # Extract sponsor info
    sponsors = bill.get("sponsors", [])
    sponsor = sponsors[0] if sponsors else {}

    # Build sponsor name
    sponsor_name = sponsor.get("fullName")
    if not sponsor_name:
        first = sponsor.get("firstName", "")
        last = sponsor.get("lastName", "")
        sponsor_name = f"{first} {last}".strip() if first or last else None

    # Extract latest action
    latest_action = bill.get("latestAction", {})

    # Extract committees
    committees = []
    committees_data = bill.get("committees", {})
    if isinstance(committees_data, dict):
        for c in committees_data.get("item", []):
            committees.append(
                {
                    "name": c.get("name"),
                    "chamber": c.get("chamber"),
                    "systemCode": c.get("systemCode"),
                }
            )

    # Extract cosponsors count
    cosponsors_data = bill.get("cosponsors", {})
    cosponsors_count = cosponsors_data.get("count", 0) if isinstance(cosponsors_data, dict) else 0

    return {
        "bill_id": bill_id,
        "congress": congress,
        "bill_type": bill_type.lower(),
        "bill_number": number,
        "title": bill.get("title", ""),
        "sponsor_name": sponsor_name,
        "sponsor_bioguide_id": sponsor.get("bioguideId"),
        "sponsor_party": sponsor.get("party"),
        "sponsor_state": sponsor.get("state"),
        "introduced_date": bill.get("introducedDate"),
        "latest_action_date": latest_action.get("actionDate"),
        "latest_action_text": latest_action.get("text"),
        "policy_area": bill.get("policyArea", {}).get("name") if bill.get("policyArea") else None,
        "committees": committees,
        "cosponsors_count": cosponsors_count,
    }


def fetch_bill_actions(congress: int, bill_type: str, number: int) -> list[dict]:
    """
    Fetch all actions for a specific bill.

    Args:
        congress: Congress number (e.g., 119)
        bill_type: Bill type (e.g., 'hr', 's')
        number: Bill number

    Returns:
        List of action dicts with keys:
        - action_date, action_text, action_type
    """
    api_key = get_api_key()

    actions = []
    offset = 0

    while True:
        url = f"{BASE_API_URL}/bill/{congress}/{bill_type.lower()}/{number}/actions?limit=100&offset={offset}"
        try:
            data = _fetch_json(url, api_key)
        except urllib.error.HTTPError as e:
            logger.error("Error fetching actions for %s-%d: %s", bill_type.upper(), number, e)
            break

        batch = data.get("actions", [])
        if not batch:
            break

        for a in batch:
            actions.append(
                {
                    "action_date": a.get("actionDate"),
                    "action_text": a.get("text", ""),
                    "action_type": a.get("type"),
                }
            )

        offset += 100
        if not data.get("pagination", {}).get("next"):
            break

    return actions


def fetch_bill_committees(congress: int, bill_type: str, bill_number: int) -> list[dict]:
    """
    Fetch committee assignments for a specific bill.

    Args:
        congress: Congress number (e.g., 119)
        bill_type: Bill type (e.g., 'hr', 's')
        bill_number: Bill number

    Returns:
        List of committee dicts with keys: name, chamber, type.
        Returns empty list on failure.
    """
    api_key = get_api_key()
    url = (
        f"{BASE_API_URL}/bill/{congress}/{bill_type.lower()}/{bill_number}"
        f"/committees?api_key={api_key}"
    )
    try:
        data = _fetch_json(url, api_key)
    except (urllib.error.HTTPError, urllib.error.URLError, Exception) as e:
        logger.error("Error fetching committees for %s-%d: %s", bill_type.upper(), bill_number, e)
        return []

    committees = []
    for c in data.get("committees", []):
        committees.append(
            {
                "name": c.get("name"),
                "chamber": c.get("chamber"),
                "type": c.get("type"),
            }
        )
    return committees


def sync_va_bills(congress: int = 119, limit: int = 250, dry_run: bool = False) -> dict:
    """
    Synchronize VA-related bills from Congress.gov to local database.

    Fetches bills from House and Senate VA committees, then fetches
    detailed information for each bill and stores new/updated records.

    Args:
        congress: Congress number to sync (default: 119)
        limit: Max bills per committee (default: 250)
        dry_run: If True, don't write to database

    Returns:
        Dict with sync results:
        - new_bills: Count of newly inserted bills
        - updated_bills: Count of bills with updated info
        - new_actions: Count of new actions recorded
        - errors: List of error messages
    """
    stats = {
        "new_bills": 0,
        "updated_bills": 0,
        "new_actions": 0,
        "errors": [],
    }

    # Collect all bills from VA committees
    all_bills = []
    for committee_code, committee_name in VA_COMMITTEES.items():
        print(f"Fetching bills from {committee_name}...")
        try:
            bills = fetch_committee_bills(committee_code, congress=congress, limit=limit)
            print(f"  Found {len(bills)} bills")
            all_bills.extend(bills)
        except Exception as e:
            error_msg = f"Error fetching {committee_name}: {e}"
            logger.error("%s", error_msg)
            stats["errors"].append(error_msg)

    # Deduplicate by (congress, bill_type, number)
    seen_bills = set()
    unique_bills = []
    for b in all_bills:
        key = (b["congress"], b["bill_type"], b["number"])
        if key not in seen_bills:
            seen_bills.add(key)
            unique_bills.append(b)

    print(f"\nProcessing {len(unique_bills)} unique bills...")

    for i, bill_meta in enumerate(unique_bills, 1):
        congress_num = bill_meta["congress"]
        bill_type = bill_meta["bill_type"]
        number = bill_meta["number"]
        bill_id = f"{bill_type}-{congress_num}-{number}"

        if i % 25 == 0:
            print(f"  Processing bill {i}/{len(unique_bills)}...")

        # Fetch detailed bill info
        try:
            details = fetch_bill_details(congress_num, bill_type, number)
        except Exception as e:
            stats["errors"].append(f"Error fetching details for {bill_id}: {e}")
            continue

        if not details:
            continue

        # Prepare bill record for db
        bill_record = {
            "bill_id": details["bill_id"],
            "congress": details["congress"],
            "bill_type": details["bill_type"],
            "bill_number": details["bill_number"],
            "title": details["title"],
            "sponsor_name": details.get("sponsor_name"),
            "sponsor_bioguide_id": details.get("sponsor_bioguide_id"),
            "sponsor_party": details.get("sponsor_party"),
            "sponsor_state": details.get("sponsor_state"),
            "introduced_date": details.get("introduced_date"),
            "latest_action_date": details.get("latest_action_date"),
            "latest_action_text": details.get("latest_action_text"),
            "policy_area": details.get("policy_area"),
            "committees_json": json.dumps(details.get("committees", [])),
            "cosponsors_count": details.get("cosponsors_count", 0),
        }

        # Upsert bill record
        if not dry_run:
            # Check if bill exists to track new vs updated
            existing = db.get_bill(bill_id)
            is_new = db.upsert_bill(bill_record)
            if is_new:
                stats["new_bills"] += 1
            elif existing:
                # Check if anything changed
                if (
                    existing.get("latest_action_date") != details.get("latest_action_date")
                    or existing.get("latest_action_text") != details.get("latest_action_text")
                    or existing.get("cosponsors_count") != details.get("cosponsors_count", 0)
                ):
                    stats["updated_bills"] += 1
        else:
            stats["new_bills"] += 1  # Assume all are new in dry-run

        # Fetch and store actions
        try:
            actions = fetch_bill_actions(congress_num, bill_type, number)
        except Exception as e:
            stats["errors"].append(f"Error fetching actions for {bill_id}: {e}")
            continue

        if actions and not dry_run:
            for action in actions:
                is_new_action = db.insert_bill_action(
                    bill_id,
                    {
                        "action_date": action["action_date"],
                        "action_text": action["action_text"],
                        "action_type": action.get("action_type"),
                    },
                )
                if is_new_action:
                    stats["new_actions"] += 1
        elif actions and dry_run:
            stats["new_actions"] += len(actions)

        # Backfill committees if empty
        if not dry_run:
            existing = db.get_bill(bill_id)
            if existing:
                cj = existing.get("committees_json")
                if not cj or cj in ("[]", "null", ""):
                    comms = fetch_bill_committees(congress_num, bill_type, number)
                    if comms:
                        db.update_committees_json(bill_id, json.dumps(comms))
                    time.sleep(0.5)

    return stats


def main():
    parser = argparse.ArgumentParser(description="Fetch VA bills from Congress.gov")
    parser.add_argument("--congress", type=int, default=119, help="Congress number (default: 119)")
    parser.add_argument(
        "--limit", type=int, default=250, help="Max bills per committee (default: 250)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Fetch but don't store in DB")
    args = parser.parse_args()

    try:
        api_key = get_api_key()
        print(f"API key found (length: {len(api_key)})")
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Ensure DB tables exist
    if not args.dry_run:
        db.init_db()

    stats = sync_va_bills(
        congress=args.congress,
        limit=args.limit,
        dry_run=args.dry_run,
    )

    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    print(f"New bills:      {stats['new_bills']}")
    print(f"Updated bills:  {stats['updated_bills']}")
    print(f"New actions:    {stats['new_actions']}")
    if stats["errors"]:
        print(f"Errors:         {len(stats['errors'])}")
        for err in stats["errors"][:5]:
            print(f"  - {err}")


if __name__ == "__main__":
    main()
