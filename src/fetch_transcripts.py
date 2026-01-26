"""
Fetch hearing transcripts from Congress.gov for agenda drift detection.

Targets VA-related committees:
- House Veterans' Affairs Committee (hsvr00)
- Senate Veterans' Affairs Committee (ssva00)

Usage:
    python -m src.fetch_transcripts [--limit N] [--congress N]
"""

import argparse
import hashlib
import json
import re
import sys
import ssl
from datetime import datetime, timezone
from typing import Optional
import urllib.request
import urllib.error

import certifi

from . import db
from .secrets import get_env_or_keychain

# VA-related committee system codes
VA_COMMITTEES = {
    "hsvr00": "House Veterans' Affairs Committee",
    "ssva00": "Senate Veterans' Affairs Committee",
    # Subcommittees
    "hsvr01": "House VA - Compensation, Pension and Insurance",
    "hsvr02": "House VA - Education, Training and Employment",
    "hsvr03": "House VA - Health",
    "hsvr04": "House VA - Housing and Memorial Affairs",
    "hsvr08": "House VA - Oversight and Investigations",
    "hsvr09": "House VA - Disability Assistance and Memorial Affairs",
    "hsvr10": "House VA - Economic Opportunity",
    "hsvr11": "House VA - Technology Modernization",
}

BASE_API_URL = "https://api.congress.gov/v3"


def get_api_key() -> str:
    """Get Congress.gov API key from environment or Keychain."""
    return get_env_or_keychain("CONGRESS_API_KEY", "congress-api")


def fetch_json(url: str, api_key: str) -> dict:
    """Fetch JSON from Congress.gov API."""
    sep = "&" if "?" in url else "?"
    full_url = f"{url}{sep}api_key={api_key}&format=json"
    req = urllib.request.Request(full_url, headers={
        "Accept": "application/json",
        "User-Agent": "VA-Signals/1.0",
    })
    context = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(req, timeout=30, context=context) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_text(url: str) -> str:
    """Fetch text/HTML content."""
    # Handle redirect to www.congress.gov
    if url.startswith("https://congress.gov"):
        url = url.replace("https://congress.gov", "https://www.congress.gov")
    req = urllib.request.Request(url, headers={"User-Agent": "VA-Signals/1.0"})
    context = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(req, timeout=60, context=context) as resp:
        return resp.read().decode("utf-8", errors="replace")


def list_hearings(api_key: str, congress: int = 118, limit: int = 100) -> list[dict]:
    """
    List hearings from Congress.gov.
    Returns list of hearing metadata with committee info.
    """
    hearings = []
    offset = 0

    while len(hearings) < limit:
        url = f"{BASE_API_URL}/hearing/{congress}?limit=100&offset={offset}"
        try:
            data = fetch_json(url, api_key)
        except urllib.error.HTTPError as e:
            print(f"Error fetching hearings page {offset}: {e}")
            break

        batch = data.get("hearings", [])
        if not batch:
            break

        for h in batch:
            hearings.append({
                "chamber": h.get("chamber"),
                "congress": h.get("congress"),
                "jacket_number": h.get("jacketNumber"),
                "url": h.get("url"),
            })

        offset += 100
        if not data.get("pagination", {}).get("next"):
            break

    return hearings[:limit]


def get_hearing_detail(api_key: str, congress: int, chamber: str, jacket_number: int) -> Optional[dict]:
    """Fetch detailed hearing info including committee and transcript URLs."""
    url = f"{BASE_API_URL}/hearing/{congress}/{chamber.lower()}/{jacket_number}"
    try:
        data = fetch_json(url, api_key)
    except urllib.error.HTTPError as e:
        print(f"Error fetching hearing detail: {e}")
        return None

    hearing = data.get("hearing", {})

    # Extract committee system codes
    committees = hearing.get("committees", [])
    committee_codes = [c.get("systemCode") for c in committees if c.get("systemCode")]

    # Find transcript URL (prefer Formatted Text over PDF)
    transcript_url = None
    for fmt in hearing.get("formats", []):
        if fmt.get("type") == "Formatted Text":
            transcript_url = fmt.get("url")
            break

    return {
        "title": hearing.get("title"),
        "congress": hearing.get("congress"),
        "chamber": hearing.get("chamber"),
        "jacket_number": jacket_number,
        "dates": [d.get("date") for d in hearing.get("dates", [])],
        "committee_codes": committee_codes,
        "committee_names": [c.get("name") for c in committees],
        "transcript_url": transcript_url,
        "hearing_id": f"{congress}-{chamber.lower()}-{jacket_number}",
    }


def is_va_hearing(committee_codes: list[str]) -> bool:
    """Check if hearing is from a VA-related committee."""
    return any(code in VA_COMMITTEES for code in committee_codes)


def parse_transcript_speakers(html_content: str) -> list[dict]:
    """
    Parse transcript HTML to extract speaker utterances.

    Returns list of dicts: {speaker_name, content, chunk_ix}
    """
    # Remove HTML tags but keep <pre> content
    # The transcript is typically in a <pre> block
    pre_match = re.search(r"<pre[^>]*>(.*?)</pre>", html_content, re.DOTALL | re.IGNORECASE)
    if pre_match:
        text = pre_match.group(1)
    else:
        # Fallback: strip all HTML
        text = re.sub(r"<[^>]+>", "", html_content)

    # Unescape HTML entities
    text = text.replace("&#x27;", "'").replace("&quot;", '"').replace("&amp;", "&")
    text = text.replace("&lt;", "<").replace("&gt;", ">")

    # Pattern for speaker turns: "Mr./Ms./Mrs./Dr./The CHAIRMAN/CHAIRWOMAN. [text]"
    # Common patterns in congressional transcripts
    speaker_pattern = re.compile(
        r"^\s{4,}((?:Mr\.|Ms\.|Mrs\.|Dr\.|The (?:CHAIRMAN|CHAIRWOMAN|CHAIR)|Chairman|Chairwoman|Senator|Representative)\s+[A-Z][a-zA-Z\-]+\.?)\s+(.+?)(?=\n\s{4,}(?:Mr\.|Ms\.|Mrs\.|Dr\.|The (?:CHAIRMAN|CHAIRWOMAN|CHAIR)|Chairman|Chairwoman|Senator|Representative)\s+[A-Z]|\Z)",
        re.MULTILINE | re.DOTALL
    )

    utterances = []
    chunk_ix = 0

    for match in speaker_pattern.finditer(text):
        speaker = match.group(1).strip().rstrip(".")
        content = match.group(2).strip()

        # Clean up content
        content = re.sub(r"\s+", " ", content)  # Normalize whitespace
        content = content.strip()

        # Skip very short utterances (likely parsing artifacts)
        if len(content) < 20:
            continue

        # Normalize speaker name
        speaker = re.sub(r"^(Mr\.|Ms\.|Mrs\.|Dr\.)\s+", "", speaker)
        speaker = re.sub(r"^The\s+(CHAIRMAN|CHAIRWOMAN|CHAIR)\s*", "Chair ", speaker, flags=re.IGNORECASE)
        speaker = speaker.strip()

        utterances.append({
            "speaker_name": speaker,
            "content": content,
            "chunk_ix": chunk_ix,
        })
        chunk_ix += 1

    return utterances


def extract_members_from_transcript(html_content: str) -> dict[str, dict]:
    """
    Extract member information from the committee roster in the transcript.

    Returns dict: {normalized_name: {name, party, state}}
    """
    members = {}

    # Look for COMMITTEE ON section with member list
    committee_section = re.search(
        r"COMMITTEE ON [A-Z\s]+\n\s*[-=]+\n(.+?)(?:\n\s*[-=]+|\n\s*SUBCOMMITTEE|\n\s*C\s*O\s*N\s*T\s*E\s*N\s*T\s*S)",
        html_content,
        re.DOTALL
    )

    if not committee_section:
        return members

    section_text = committee_section.group(1)

    # Pattern for member lines: NAME, State
    # e.g., "JIM JORDAN, Ohio, Chair" or "JAMIE RASKIN, Maryland, Ranking Member"
    member_pattern = re.compile(
        r"([A-Z][A-Z\s\.\-\']+),\s+([A-Za-z\s]+?)(?:,\s+(?:Chair|Ranking|Member))?$",
        re.MULTILINE
    )

    for match in member_pattern.finditer(section_text):
        full_name = match.group(1).strip()
        state = match.group(2).strip()

        # Normalize name to Title Case
        name = " ".join(word.capitalize() for word in full_name.split())

        # Derive last name for matching with speaker turns
        parts = name.split()
        if parts:
            last_name = parts[-1].upper()
            members[last_name] = {
                "name": name,
                "state": state,
                "party": None,  # Would need additional API call to get party
            }

    return members


def generate_member_id(name: str, congress: int) -> str:
    """Generate a stable member ID from name."""
    normalized = name.lower().replace(" ", "-").replace(".", "")
    return f"{normalized}-{congress}"


def generate_utterance_id(hearing_id: str, speaker: str, chunk_ix: int) -> str:
    """Generate unique utterance ID."""
    content = f"{hearing_id}:{speaker}:{chunk_ix}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def process_hearing(api_key: str, hearing_meta: dict, dry_run: bool = False) -> dict:
    """
    Process a single hearing: fetch transcript, parse utterances, store in DB.

    Returns stats dict: {hearing_id, members_added, utterances_added, errors}
    """
    stats = {
        "hearing_id": hearing_meta.get("hearing_id", "unknown"),
        "members_added": 0,
        "utterances_added": 0,
        "errors": [],
    }

    # Get detailed hearing info
    detail = get_hearing_detail(
        api_key,
        hearing_meta["congress"],
        hearing_meta["chamber"],
        hearing_meta["jacket_number"],
    )

    if not detail:
        stats["errors"].append("Failed to fetch hearing detail")
        return stats

    stats["hearing_id"] = detail["hearing_id"]

    # Check if VA-related
    if not is_va_hearing(detail.get("committee_codes", [])):
        stats["errors"].append("Not a VA hearing")
        return stats

    # Fetch transcript
    if not detail.get("transcript_url"):
        stats["errors"].append("No transcript URL available")
        return stats

    try:
        transcript_html = fetch_text(detail["transcript_url"])
    except Exception as e:
        stats["errors"].append(f"Failed to fetch transcript: {e}")
        return stats

    # Extract members
    members_info = extract_members_from_transcript(transcript_html)

    # Parse utterances
    utterances = parse_transcript_speakers(transcript_html)

    if not utterances:
        stats["errors"].append("No utterances parsed from transcript")
        return stats

    # Determine hearing date
    hearing_date = detail["dates"][0] if detail.get("dates") else datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Prepare data for DB
    db_utterances = []
    member_ids_seen = set()

    for utt in utterances:
        speaker = utt["speaker_name"].upper()

        # Try to match speaker to a known member
        member_info = members_info.get(speaker)
        if not member_info:
            # Try last name only
            last_name = speaker.split()[-1] if speaker else ""
            member_info = members_info.get(last_name)

        # Generate member ID
        display_name = member_info["name"] if member_info else utt["speaker_name"]
        member_id = generate_member_id(display_name, detail["congress"])

        # Register member if new
        if member_id not in member_ids_seen and not dry_run:
            is_new = db.upsert_ad_member(
                member_id=member_id,
                name=display_name,
                party=member_info.get("party") if member_info else None,
                committee=detail["committee_names"][0] if detail.get("committee_names") else None,
            )
            if is_new:
                stats["members_added"] += 1
            member_ids_seen.add(member_id)

        # Prepare utterance record
        db_utterances.append({
            "utterance_id": generate_utterance_id(detail["hearing_id"], display_name, utt["chunk_ix"]),
            "member_id": member_id,
            "hearing_id": detail["hearing_id"],
            "chunk_ix": utt["chunk_ix"],
            "content": utt["content"][:10000],  # Truncate very long utterances
            "spoken_at": hearing_date,
        })

    # Bulk insert utterances
    if not dry_run and db_utterances:
        inserted = db.bulk_insert_ad_utterances(db_utterances)
        stats["utterances_added"] = inserted
    elif dry_run:
        stats["utterances_added"] = len(db_utterances)

    return stats


def fetch_va_hearings(api_key: str, congress: int = 118, limit: int = 50, dry_run: bool = False) -> dict:
    """
    Main entry point: fetch and process VA-related hearings.

    Returns summary stats.
    """
    print(f"Fetching hearings for Congress {congress}...")

    # List all hearings
    all_hearings = list_hearings(api_key, congress=congress, limit=limit * 5)  # Fetch more to filter
    print(f"Found {len(all_hearings)} total hearings")

    # Process hearings and filter for VA
    total_stats = {
        "hearings_processed": 0,
        "va_hearings_found": 0,
        "members_added": 0,
        "utterances_added": 0,
        "errors": [],
    }

    va_count = 0
    for hearing in all_hearings:
        if va_count >= limit:
            break

        # Get detail to check committee
        detail = get_hearing_detail(
            api_key,
            hearing["congress"],
            hearing["chamber"],
            hearing["jacket_number"],
        )

        if not detail:
            continue

        total_stats["hearings_processed"] += 1

        if not is_va_hearing(detail.get("committee_codes", [])):
            continue

        va_count += 1
        total_stats["va_hearings_found"] += 1

        print(f"\nProcessing VA hearing: {detail['title'][:60]}...")
        print(f"  Committees: {', '.join(detail.get('committee_names', []))}")

        stats = process_hearing(api_key, {
            "congress": hearing["congress"],
            "chamber": hearing["chamber"],
            "jacket_number": hearing["jacket_number"],
        }, dry_run=dry_run)

        total_stats["members_added"] += stats["members_added"]
        total_stats["utterances_added"] += stats["utterances_added"]

        if stats["errors"]:
            total_stats["errors"].extend(stats["errors"])
            print(f"  Errors: {stats['errors']}")
        else:
            print(f"  Added: {stats['members_added']} members, {stats['utterances_added']} utterances")

    return total_stats


def main():
    parser = argparse.ArgumentParser(description="Fetch hearing transcripts from Congress.gov")
    parser.add_argument("--congress", type=int, default=118, help="Congress number (default: 118)")
    parser.add_argument("--limit", type=int, default=10, help="Max VA hearings to process (default: 10)")
    parser.add_argument("--dry-run", action="store_true", help="Parse but don't store in DB")
    args = parser.parse_args()

    try:
        api_key = get_api_key()
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Ensure DB tables exist
    if not args.dry_run:
        db.init_db()

    stats = fetch_va_hearings(
        api_key,
        congress=args.congress,
        limit=args.limit,
        dry_run=args.dry_run,
    )

    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    print(f"Hearings scanned:    {stats['hearings_processed']}")
    print(f"VA hearings found:   {stats['va_hearings_found']}")
    print(f"Members added:       {stats['members_added']}")
    print(f"Utterances added:    {stats['utterances_added']}")
    if stats["errors"]:
        print(f"Errors:              {len(stats['errors'])}")


if __name__ == "__main__":
    main()
