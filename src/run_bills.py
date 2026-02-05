"""
VA Bills Sync Runner

Usage:
    python -m src.run_bills [--full] [--summary]
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import validate

# Allow running as a script (python src/run_bills.py) by setting package context
if __name__ == "__main__" and __package__ is None:
    import sys
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    __package__ = "src"

from .db import init_db, insert_source_run, get_bill_stats, get_bills, get_new_bills_since, get_new_actions_since
from .fetch_bills import sync_va_bills
from .notify_email import send_error_alert
from .provenance import utc_now_iso

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ID = "congress_bills"


def load_run_schema() -> dict[str, Any]:
    return json.loads((ROOT / "schemas" / "source_run.schema.json").read_text(encoding="utf-8"))


def write_run_record(run_record: dict[str, Any]) -> None:
    outdir = ROOT / "outputs" / "runs"
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    (outdir / f"BILLS_{stamp}.json").write_text(json.dumps(run_record, indent=2), encoding="utf-8")


def run_bills_sync(full: bool = False, congress: int = 118) -> dict[str, Any]:
    """
    Run VA bills sync.

    Args:
        full: If True, perform full sync (future: could expand coverage)
        congress: Congress number to sync (default: 118th)

    Returns:
        Run record dict
    """
    init_db()
    schema = load_run_schema()

    started_at = utc_now_iso()
    errors: list[str] = []
    status = "SUCCESS"

    try:
        sync_result = sync_va_bills(congress=congress)
        new_bills_count = sync_result["new_bills"]
        new_actions_count = sync_result["new_actions"]
        records_fetched = new_bills_count + sync_result.get("updated_bills", 0)
        errors.extend(sync_result.get("errors", []))

        if sync_result.get("errors"):
            status = "ERROR"
        elif not new_bills_count and not new_actions_count:
            status = "NO_DATA"

    except Exception as e:
        status = "ERROR"
        errors.append(f"EXCEPTION: {repr(e)}")
        new_bills_count = 0
        new_actions_count = 0
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
    new_bills = get_new_bills_since(started_at) if new_bills_count else []
    new_actions = get_new_actions_since(started_at) if new_actions_count else []

    # Write latest results
    outdir = ROOT / "outputs" / "runs"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "BILLS_LATEST.json").write_text(
        json.dumps({
            "retrieved_at": utc_now_iso(),
            "new_bills_count": new_bills_count,
            "new_actions_count": new_actions_count,
        }, indent=2),
        encoding="utf-8",
    )

    # Print summary
    summary = {
        "run_record": run_record,
        "new_bills_count": new_bills_count,
        "new_actions_count": new_actions_count,
        "bills_updated": sync_result.get("updated_bills", 0) if status != "ERROR" else 0,
    }
    print(json.dumps(summary, indent=2))

    # Send error email if needed
    if status == "ERROR" and errors:
        send_error_alert(SOURCE_ID, errors, run_record)

    return run_record


def print_summary():
    """Print bills tracking summary."""
    stats = get_bill_stats()
    recent = get_bills(limit=10)

    print("\n" + "=" * 60)
    print("VA BILLS TRACKING - STATUS")
    print("=" * 60)
    print(f"Total bills tracked:  {stats['total_bills']}")
    print(f"Total actions logged: {stats['total_actions']}")
    if stats.get('by_congress'):
        print(f"By congress:          {stats['by_congress']}")

    if recent:
        print("\nRecent Bills:")
        print("-" * 60)
        for bill in recent[:5]:
            bill_ref = f"{bill['bill_type']} {bill['bill_number']}"
            sponsor = ""
            if bill["sponsor_name"]:
                sponsor = f" ({bill['sponsor_name']}"
                if bill["sponsor_party"] and bill["sponsor_state"]:
                    sponsor += f", {bill['sponsor_party']}-{bill['sponsor_state']}"
                sponsor += ")"
            title = bill["title"][:50] + "..." if len(bill["title"]) > 50 else bill["title"]
            print(f"  {bill_ref}: {title}{sponsor}")


def main():
    parser = argparse.ArgumentParser(description="Run VA bills sync")
    parser.add_argument("--full", action="store_true", help="Full sync of all VA committee bills")
    parser.add_argument("--summary", action="store_true", help="Show stats only")
    parser.add_argument("--congress", type=int, default=118, help="Congress number (default: 118)")
    args = parser.parse_args()

    init_db()

    if args.summary:
        print_summary()
        return

    # Default: run sync
    run_bills_sync(full=args.full, congress=args.congress)
    print_summary()


if __name__ == "__main__":
    main()
