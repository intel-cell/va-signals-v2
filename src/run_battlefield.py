#!/usr/bin/env python3
"""
Battlefield Dashboard Runner

Runs calendar sync and gate detection for the battlefield dashboard.
Can be invoked manually or via cron/scheduler.

Usage:
    python -m src.run_battlefield --sync        # Sync all sources
    python -m src.run_battlefield --detect      # Run gate detection
    python -m src.run_battlefield --all         # Sync + detect
    python -m src.run_battlefield --init        # Initialize tables
    python -m src.run_battlefield --stats       # Show stats
"""

import argparse
import json
import logging
import sys
from datetime import datetime

from src.db import insert_source_run
from src.notify_email import send_error_alert
from src.provenance import utc_now_iso

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def init_tables():
    """Initialize battlefield database tables."""
    from src.battlefield.db_helpers import init_battlefield_tables

    logger.info("Initializing battlefield tables...")
    init_battlefield_tables()
    logger.info("Tables initialized successfully.")


def run_sync():
    """Sync all sources to battlefield."""
    from src.battlefield.calendar import sync_all_sources

    started_at = utc_now_iso()
    errors = []
    status = "SUCCESS"
    records_fetched = 0

    logger.info("Starting battlefield sync...")

    try:
        results = sync_all_sources()

        total_vehicles = sum(r.get("created_vehicles", 0) for r in results.values())
        total_events = sum(r.get("created_events", 0) for r in results.values())
        records_fetched = total_vehicles + total_events

        logger.info(f"Sync complete: {total_vehicles} vehicles, {total_events} events")
        logger.info(f"Results: {json.dumps(results, indent=2)}")

    except Exception as e:
        status = "ERROR"
        errors.append(f"EXCEPTION: {repr(e)}")
        logger.error(f"Sync failed: {e}", exc_info=True)
        results = {}

    ended_at = utc_now_iso()

    run_record = {
        "source_id": "battlefield_sync",
        "started_at": started_at,
        "ended_at": ended_at,
        "status": status,
        "records_fetched": records_fetched,
        "errors": errors,
    }

    try:
        insert_source_run(run_record)
    except Exception as e:
        logger.error(f"Failed to insert run record: {e}")

    if status == "ERROR":
        send_error_alert("battlefield_sync", errors, run_record)

    return results


def run_detection():
    """Run gate detection."""
    from src.battlefield.gate_detection import run_all_detections

    started_at = utc_now_iso()
    errors = []
    status = "SUCCESS"
    records_fetched = 0

    logger.info("Starting gate detection...")

    try:
        results = run_all_detections()

        total_alerts = sum(r.get("alerts_created", 0) for r in results.values())
        records_fetched = total_alerts

        logger.info(f"Detection complete: {total_alerts} alerts created")
        logger.info(f"Results: {json.dumps(results, indent=2)}")

    except Exception as e:
        status = "ERROR"
        errors.append(f"EXCEPTION: {repr(e)}")
        logger.error(f"Detection failed: {e}", exc_info=True)
        results = {}

    ended_at = utc_now_iso()

    run_record = {
        "source_id": "battlefield_detection",
        "started_at": started_at,
        "ended_at": ended_at,
        "status": status,
        "records_fetched": records_fetched,
        "errors": errors,
    }

    try:
        insert_source_run(run_record)
    except Exception as e:
        logger.error(f"Failed to insert run record: {e}")

    if status == "ERROR":
        send_error_alert("battlefield_detection", errors, run_record)

    return results


def show_stats():
    """Show dashboard statistics."""
    from src.battlefield.db_helpers import get_critical_gates, get_dashboard_stats

    stats = get_dashboard_stats()
    gates = get_critical_gates(days=14)

    print("\n" + "=" * 60)
    print("BATTLEFIELD DASHBOARD STATUS")
    print("=" * 60)
    print(f"\nGenerated: {datetime.utcnow().isoformat()}")

    print(f"\nVEHICLES: {stats['total_vehicles']} total")
    for vtype, count in stats["by_type"].items():
        print(f"  - {vtype}: {count}")

    print("\nPOSTURE:")
    for posture, count in stats["by_posture"].items():
        print(f"  - {posture}: {count}")

    print(f"\nGATES (next 14 days): {stats['upcoming_gates_14d']}")
    if gates:
        for gate in gates[:5]:
            print(f"  - {gate['date']}: {gate['title'][:50]}...")

    print(f"\nALERTS (48h): {stats['alerts_48h']}")
    print(f"  Unacknowledged: {stats['unacknowledged_alerts']}")

    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Battlefield Dashboard Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m src.run_battlefield --init        # Initialize tables (run once)
    python -m src.run_battlefield --sync        # Sync hearings, bills, FR, oversight
    python -m src.run_battlefield --detect      # Detect gate changes
    python -m src.run_battlefield --all         # Full sync + detection
    python -m src.run_battlefield --stats       # Show current stats
        """,
    )

    parser.add_argument("--init", action="store_true", help="Initialize database tables")
    parser.add_argument("--sync", action="store_true", help="Sync all sources")
    parser.add_argument("--detect", action="store_true", help="Run gate detection")
    parser.add_argument("--all", action="store_true", help="Run sync and detection")
    parser.add_argument("--stats", action="store_true", help="Show dashboard stats")

    args = parser.parse_args()

    # If no args, show help
    if not any([args.init, args.sync, args.detect, args.all, args.stats]):
        parser.print_help()
        sys.exit(0)

    try:
        if args.init:
            init_tables()

        if args.sync or args.all:
            run_sync()

        if args.detect or args.all:
            run_detection()

        if args.stats:
            show_stats()

    except Exception as e:
        logger.error(f"Battlefield run failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
