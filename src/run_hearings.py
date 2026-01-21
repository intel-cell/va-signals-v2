"""
VA Hearings Sync Runner

Usage:
    python -m src.run_hearings [--full] [--summary]
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import validate

# Allow running as a script (python src/run_hearings.py) by setting package context
if __name__ == "__main__" and __package__ is None:
    import sys
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    __package__ = "src"

from .db import init_db, insert_source_run, get_hearing_stats, get_hearings, get_new_hearings_since, get_hearing_changes_since
from .fetch_hearings import sync_va_hearings
from .notify_slack import post_slack, format_new_hearings_alert, format_hearing_changes_alert
from .provenance import utc_now_iso

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ID = "congress_hearings"


def load_run_schema() -> dict[str, Any]:
    return json.loads((ROOT / "schemas" / "source_run.schema.json").read_text(encoding="utf-8"))


def write_run_record(run_record: dict[str, Any]) -> None:
    outdir = ROOT / "outputs" / "runs"
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    (outdir / f"HEARINGS_{stamp}.json").write_text(json.dumps(run_record, indent=2), encoding="utf-8")


def run_hearings_sync(full: bool = False, congress: int = 119) -> dict[str, Any]:
    """
    Run VA hearings sync.

    Args:
        full: If True, perform full sync (larger limit)
        congress: Congress number to sync (default: 119)

    Returns:
        Run record dict
    """
    init_db()
    schema = load_run_schema()

    started_at = utc_now_iso()
    errors: list[str] = []
    status = "SUCCESS"

    try:
        # Full sync uses higher limit
        limit = 250 if full else 100
        sync_result = sync_va_hearings(congress=congress, limit=limit)
        new_hearings_count = sync_result["new_hearings"]
        updated_hearings_count = sync_result["updated_hearings"]
        changes = sync_result.get("changes", [])
        records_fetched = new_hearings_count + updated_hearings_count
        errors.extend(sync_result.get("errors", []))

        if sync_result.get("errors"):
            status = "ERROR"
        elif not new_hearings_count and not updated_hearings_count:
            status = "NO_DATA"

    except Exception as e:
        status = "ERROR"
        errors.append(f"EXCEPTION: {repr(e)}")
        new_hearings_count = 0
        updated_hearings_count = 0
        changes = []
        records_fetched = 0

    ended_at = utc_now_iso()

    run_record = {
        "source_id": SOURCE_ID,
        "started_at": started_at,
        "ended_at": ended_at,
        "status": status,
        "records_fetched": records_fetched,
        "errors": errors,
    }

    validate(instance=run_record, schema=schema)
    insert_source_run(run_record)
    write_run_record(run_record)

    # Get new items from DB for alerts
    new_hearings = get_new_hearings_since(started_at) if new_hearings_count else []
    hearing_changes = get_hearing_changes_since(started_at) if updated_hearings_count else []

    # Write latest results
    outdir = ROOT / "outputs" / "runs"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "HEARINGS_LATEST.json").write_text(
        json.dumps({
            "retrieved_at": utc_now_iso(),
            "new_hearings_count": new_hearings_count,
            "updated_hearings_count": updated_hearings_count,
            "changes_count": len(changes),
        }, indent=2),
        encoding="utf-8",
    )

    # Print summary
    summary = {
        "run_record": run_record,
        "new_hearings_count": new_hearings_count,
        "updated_hearings_count": updated_hearings_count,
        "changes_count": len(changes),
    }
    print(json.dumps(summary, indent=2))

    # Send Slack alerts
    if new_hearings:
        alert_payload = format_new_hearings_alert(new_hearings)
        if alert_payload:
            try:
                post_slack(alert_payload)
            except Exception:
                pass

    if hearing_changes:
        alert_payload = format_hearing_changes_alert(hearing_changes)
        if alert_payload:
            try:
                post_slack(alert_payload)
            except Exception:
                pass

    return run_record


def print_summary():
    """Print hearings tracking summary."""
    stats = get_hearing_stats()
    upcoming = get_hearings(upcoming=True, limit=10)

    print("\n" + "=" * 60)
    print("VA HEARINGS TRACKING - STATUS")
    print("=" * 60)
    print(f"Total hearings tracked: {stats['total']}")
    print(f"Upcoming hearings:      {stats['upcoming']}")

    if stats.get('by_committee'):
        print(f"\nBy committee:")
        for code, info in stats['by_committee'].items():
            print(f"  {code}: {info['count']} ({info['name']})")

    if stats.get('by_status'):
        print(f"\nBy status:")
        for status, count in stats['by_status'].items():
            print(f"  {status}: {count}")

    if upcoming:
        print("\nUpcoming Hearings:")
        print("-" * 60)
        for hearing in upcoming[:5]:
            date_str = hearing["hearing_date"] or "TBD"
            time_str = hearing.get("hearing_time") or ""
            if time_str:
                date_str = f"{date_str} {time_str}"

            committee = hearing.get("committee_code", "").upper()
            if committee.startswith("H"):
                committee = "HVAC"
            elif committee.startswith("S"):
                committee = "SVAC"

            title = hearing.get("title") or "(No title)"
            if len(title) > 45:
                title = title[:42] + "..."

            status = hearing.get("status", "")
            status_str = f" [{status}]" if status and status.lower() != "scheduled" else ""

            print(f"  {date_str}: {committee} - {title}{status_str}")


def main():
    parser = argparse.ArgumentParser(description="Run VA hearings sync")
    parser.add_argument("--full", action="store_true", help="Full sync of all VA committee hearings")
    parser.add_argument("--summary", action="store_true", help="Show stats only")
    parser.add_argument("--congress", type=int, default=119, help="Congress number (default: 119)")
    args = parser.parse_args()

    init_db()

    if args.summary:
        print_summary()
        return

    # Default: run sync
    run_hearings_sync(full=args.full, congress=args.congress)
    print_summary()


if __name__ == "__main__":
    main()
