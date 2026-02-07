"""
VA Hearings Fetcher

Fetches committee hearings from Congress.gov API for VA committees.

Targets VA committees:
- House Veterans' Affairs Committee (hsvr00)
- Senate Veterans' Affairs Committee (ssva00)

Usage:
    python -m src.fetch_hearings [--congress N] [--limit N] [--dry-run]
"""

import argparse
import json
import ssl
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime

import certifi

from . import db
from .resilience.circuit_breaker import congress_api_cb
from .resilience.wiring import circuit_breaker_sync, with_timeout
from .secrets import get_env_or_keychain

# Congress.gov API base URL
API_BASE = "https://api.congress.gov/v3"

# VA-related committee system codes (full committees + subcommittees)
VA_COMMITTEES = {
    # House Veterans' Affairs - Full Committee
    "hsvr00": "house",
    # House VA Subcommittees
    "hsvr01": "house",  # Compensation, Pension and Insurance
    "hsvr02": "house",  # Education, Training and Employment
    "hsvr03": "house",  # Health
    "hsvr04": "house",  # Housing and Memorial Affairs
    "hsvr08": "house",  # Oversight and Investigations
    "hsvr10": "house",  # Economic Opportunity
    "hsvr11": "house",  # Technology Modernization
    # Senate Veterans' Affairs - Full Committee
    "ssva00": "senate",
}

# Committee names for display
VA_COMMITTEE_NAMES = {
    # House VA
    "hsvr00": "House Veterans' Affairs Committee",
    "hsvr01": "House VA Subcommittee on Compensation, Pension and Insurance",
    "hsvr02": "House VA Subcommittee on Education, Training and Employment",
    "hsvr03": "House VA Subcommittee on Health",
    "hsvr04": "House VA Subcommittee on Housing and Memorial Affairs",
    "hsvr08": "House VA Subcommittee on Oversight and Investigations",
    "hsvr10": "House VA Subcommittee on Economic Opportunity",
    "hsvr11": "House VA Subcommittee on Technology Modernization",
    # Senate VA
    "ssva00": "Senate Veterans' Affairs Committee",
}

# Current congress
CURRENT_CONGRESS = 119


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


def fetch_committee_meetings(
    chamber: str, congress: int = CURRENT_CONGRESS, limit: int = 100
) -> list[dict]:
    """
    Fetch committee meetings for a chamber.

    GET /committee-meeting/{congress}/{chamber}

    Args:
        chamber: 'house' or 'senate'
        congress: Congress number (default: 119)
        limit: Maximum number of meetings to fetch

    Returns:
        List of meeting dicts with keys:
        - eventId, date, title, type, meetingStatus, committees, etc.
    """
    api_key = get_api_key()

    meetings = []
    offset = 0

    while len(meetings) < limit:
        url = f"{API_BASE}/committee-meeting/{congress}/{chamber}?limit=100&offset={offset}"
        try:
            data = _fetch_json(url, api_key)
        except urllib.error.HTTPError as e:
            print(f"Error fetching committee meetings page {offset}: {e}")
            break

        batch = data.get("committeeMeetings", [])
        if not batch:
            break

        meetings.extend(batch)
        offset += 100

        # Check pagination
        if not data.get("pagination", {}).get("next"):
            break

    return meetings[:limit]


def fetch_meeting_details(congress: int, chamber: str, event_id: str) -> dict | None:
    """
    Fetch full meeting details including witnesses.

    GET /committee-meeting/{congress}/{chamber}/{eventId}

    Args:
        congress: Congress number
        chamber: 'house' or 'senate'
        event_id: Meeting event ID

    Returns:
        Dict with meeting details or None if not found
    """
    api_key = get_api_key()

    url = f"{API_BASE}/committee-meeting/{congress}/{chamber}/{event_id}"
    try:
        data = _fetch_json(url, api_key)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        print(f"Error fetching meeting details for {event_id}: {e}")
        return None

    return data.get("committeeMeeting")


def is_va_committee_meeting(meeting: dict) -> tuple[bool, str | None]:
    """
    Check if meeting involves a VA committee.

    Args:
        meeting: Meeting dict from API

    Returns:
        Tuple of (is_va_meeting, committee_code)
    """
    committees = meeting.get("committees", [])
    for committee in committees:
        system_code = committee.get("systemCode", "").lower()
        if system_code in VA_COMMITTEES:
            return True, system_code
    return False, None


def sync_va_hearings(
    congress: int = CURRENT_CONGRESS, limit: int = 100, dry_run: bool = False
) -> dict:
    """
    Main sync function for VA committee hearings.

    1. Fetch meetings from House and Senate
    2. Filter to VA committees (hsvr00, ssva00)
    3. Fetch details for each VA meeting
    4. Upsert to DB, detect new and changed hearings

    Args:
        congress: Congress number to sync (default: 119)
        limit: Max meetings per chamber to fetch (default: 100)
        dry_run: If True, don't write to database

    Returns:
        Stats dict: {new_hearings: N, updated_hearings: N, changes: [...], errors: [...]}
    """
    stats = {
        "new_hearings": 0,
        "updated_hearings": 0,
        "changes": [],
        "errors": [],
    }

    # Fetch meetings from both chambers and filter to VA committees
    # Note: List endpoint doesn't include committee info, so we fetch details for each
    all_va_meetings = []

    for chamber in ["house", "senate"]:
        print(f"Fetching {chamber.title()} committee meetings...")
        try:
            meetings = fetch_committee_meetings(chamber, congress=congress, limit=limit)
            print(f"  Found {len(meetings)} meetings, checking for VA committees...")

            # Fetch details for each meeting to get committee info
            va_count = 0
            for i, meeting in enumerate(meetings):
                event_id = meeting.get("eventId")
                if not event_id:
                    continue

                # Fetch full details to get committee info
                try:
                    details = fetch_meeting_details(congress, chamber, event_id)
                except Exception:
                    continue

                if not details:
                    continue

                # Now check if it's a VA committee meeting
                is_va, committee_code = is_va_committee_meeting(details)
                if is_va:
                    details["_chamber"] = chamber
                    details["_committee_code"] = committee_code
                    all_va_meetings.append(details)
                    va_count += 1

                # Progress indicator
                if (i + 1) % 25 == 0:
                    print(f"    Checked {i + 1}/{len(meetings)} meetings, found {va_count} VA...")

            print(f"  {va_count} are VA committee meetings")

        except Exception as e:
            error_msg = f"Error fetching {chamber} meetings: {e}"
            print(f"  {error_msg}")
            stats["errors"].append(error_msg)

    print(f"\nProcessing {len(all_va_meetings)} VA committee meetings...")

    for i, details in enumerate(all_va_meetings, 1):
        event_id = details.get("eventId")
        if not event_id:
            continue

        chamber = details["_chamber"]
        committee_code = details["_committee_code"]

        if i % 10 == 0:
            print(f"  Processing meeting {i}/{len(all_va_meetings)}...")

        # Extract witnesses if available
        witnesses = []
        if "witnesses" in details:
            for w in details.get("witnesses", []):
                witnesses.append(
                    {
                        "name": w.get("name"),
                        "position": w.get("position"),
                        "organization": w.get("organization"),
                    }
                )

        # Extract committee info
        committees = details.get("committees", [])
        committee_name = None
        for c in committees:
            if c.get("systemCode", "").lower() == committee_code:
                committee_name = c.get("name")
                break
        if not committee_name:
            committee_name = VA_COMMITTEE_NAMES.get(committee_code, "")

        # Extract location as string
        location_data = details.get("location")
        if isinstance(location_data, dict):
            room = location_data.get("room", "")
            building = location_data.get("building", "")
            location = f"{room}, {building}".strip(", ") if room or building else None
        else:
            location = location_data

        # Extract hearing time from date if available (date might include time)
        date_str = details.get("date", "")
        hearing_date = date_str[:10] if date_str else None  # YYYY-MM-DD
        hearing_time = None
        if date_str and "T" in date_str:
            time_part = date_str.split("T")[1][:5]  # HH:MM
            if time_part != "00:00":  # Don't use midnight as a real time
                hearing_time = time_part

        # Build hearing record
        hearing_record = {
            "event_id": str(event_id),
            "congress": congress,
            "chamber": chamber,
            "committee_code": committee_code,
            "committee_name": committee_name,
            "hearing_date": hearing_date,
            "hearing_time": hearing_time,
            "title": details.get("title"),
            "meeting_type": details.get("type"),
            "status": details.get("meetingStatus", "unknown"),
            "location": location,
            "url": f"https://www.congress.gov/event/{congress}th-congress/house-committee/{event_id}"
            if chamber == "house"
            else f"https://www.congress.gov/event/{congress}th-congress/senate-committee/{event_id}",
            "witnesses_json": json.dumps(witnesses) if witnesses else None,
        }

        # Upsert to DB
        if not dry_run:
            is_new, changes = db.upsert_hearing(hearing_record)
            if is_new:
                stats["new_hearings"] += 1
            elif changes:
                stats["updated_hearings"] += 1
                for change in changes:
                    stats["changes"].append(
                        {
                            "event_id": event_id,
                            "field": change["field_changed"],
                            "old_value": change["old_value"],
                            "new_value": change["new_value"],
                        }
                    )
        else:
            stats["new_hearings"] += 1  # Assume all are new in dry-run

    return stats


def main():
    parser = argparse.ArgumentParser(description="Fetch VA committee hearings from Congress.gov")
    parser.add_argument(
        "--congress",
        type=int,
        default=CURRENT_CONGRESS,
        help=f"Congress number (default: {CURRENT_CONGRESS})",
    )
    parser.add_argument(
        "--limit", type=int, default=100, help="Max meetings per chamber (default: 100)"
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

    stats = sync_va_hearings(
        congress=args.congress,
        limit=args.limit,
        dry_run=args.dry_run,
    )

    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    print(f"New hearings:     {stats['new_hearings']}")
    print(f"Updated hearings: {stats['updated_hearings']}")

    if stats["changes"]:
        print(f"\nChanges detected ({len(stats['changes'])}):")
        for change in stats["changes"][:10]:
            print(f"  - {change['event_id']}: {change['field']} changed")
            print(f"      old: {change['old_value']}")
            print(f"      new: {change['new_value']}")
        if len(stats["changes"]) > 10:
            print(f"  ... and {len(stats['changes']) - 10} more")

    if stats["errors"]:
        print(f"\nErrors ({len(stats['errors'])}):")
        for err in stats["errors"][:5]:
            print(f"  - {err}")


if __name__ == "__main__":
    main()
