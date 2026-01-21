#!/usr/bin/env python
"""
CLI runner for Oversight Monitor.

Usage:
    python -m src.run_oversight                    # Run all agents
    python -m src.run_oversight --agent gao        # Run single agent
    python -m src.run_oversight --backfill gao --start 2025-10-01 --end 2026-01-01
    python -m src.run_oversight --digest --start 2026-01-13 --end 2026-01-20
    python -m src.run_oversight --status           # Show system status
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone

from .oversight.runner import (
    run_agent,
    run_all_agents,
    run_backfill,
    generate_digest,
    init_oversight,
    AGENT_REGISTRY,
)
from .db import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def cmd_run(args):
    """Run agents."""
    init_db()
    init_oversight()

    since = None
    if args.since:
        since = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)

    if args.agent:
        result = run_agent(args.agent, since=since)
        print(f"\n{result.agent}: {result.status}")
        print(f"  Fetched: {result.events_fetched}")
        print(f"  Processed: {result.events_processed}")
        print(f"  Escalations: {result.escalations}")
        if result.errors:
            print(f"  Errors: {result.errors}")
    else:
        results = run_all_agents(since=since)
        print("\n=== Oversight Monitor Run Complete ===")
        for r in results:
            status_icon = "✓" if r.status == "SUCCESS" else "○" if r.status == "NO_DATA" else "✗"
            print(f"{status_icon} {r.agent}: {r.events_processed} processed, {r.escalations} escalations")


def cmd_backfill(args):
    """Backfill historical data."""
    init_db()
    init_oversight()

    result = run_backfill(
        agent_name=args.agent,
        start_date=args.start,
        end_date=args.end,
    )

    print(f"\nBackfill {args.agent}: {result.status}")
    print(f"  Fetched: {result.events_fetched}")
    print(f"  Processed: {result.events_processed}")


def cmd_digest(args):
    """Generate weekly digest."""
    init_db()

    digest = generate_digest(
        start_date=args.start,
        end_date=args.end,
    )

    if args.output:
        with open(args.output, "w") as f:
            f.write(digest)
        print(f"Digest written to {args.output}")
    else:
        print(digest)


def cmd_status(args):
    """Show system status."""
    init_db()

    from .db import connect

    con = connect()

    # Count events
    cur = con.execute("SELECT COUNT(*) FROM om_events")
    event_count = cur.fetchone()[0]

    # Count by source
    cur = con.execute(
        "SELECT primary_source_type, COUNT(*) FROM om_events GROUP BY primary_source_type"
    )
    by_source = dict(cur.fetchall())

    # Recent events
    cur = con.execute(
        "SELECT event_id, title, pub_timestamp FROM om_events ORDER BY pub_timestamp DESC LIMIT 5"
    )
    recent = cur.fetchall()

    # Escalations
    cur = con.execute("SELECT COUNT(*) FROM om_events WHERE is_escalation = 1")
    escalation_count = cur.fetchone()[0]

    con.close()

    print("\n=== Oversight Monitor Status ===")
    print(f"Total events: {event_count}")
    print(f"Escalations: {escalation_count}")
    print(f"\nBy source:")
    for source, count in by_source.items():
        print(f"  {source}: {count}")
    print(f"\nRegistered agents: {', '.join(AGENT_REGISTRY.keys())}")
    print(f"\nRecent events:")
    for eid, title, ts in recent:
        print(f"  [{ts[:10]}] {title[:60]}")


def main():
    parser = argparse.ArgumentParser(description="Oversight Monitor CLI")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Run command (default)
    run_parser = subparsers.add_parser("run", help="Run oversight agents")
    run_parser.add_argument("--agent", "-a", help="Run specific agent")
    run_parser.add_argument("--since", help="Only fetch events since (ISO date)")

    # Backfill command
    backfill_parser = subparsers.add_parser("backfill", help="Backfill historical data")
    backfill_parser.add_argument("--agent", "-a", required=True, help="Agent to backfill")
    backfill_parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    backfill_parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")

    # Digest command
    digest_parser = subparsers.add_parser("digest", help="Generate weekly digest")
    digest_parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    digest_parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    digest_parser.add_argument("--output", "-o", help="Output file (default: stdout)")

    # Status command
    subparsers.add_parser("status", help="Show system status")

    args = parser.parse_args()

    if args.command == "backfill":
        cmd_backfill(args)
    elif args.command == "digest":
        cmd_digest(args)
    elif args.command == "status":
        cmd_status(args)
    else:
        # Default to run
        if not hasattr(args, "agent"):
            args.agent = None
        if not hasattr(args, "since"):
            args.since = None
        cmd_run(args)


if __name__ == "__main__":
    main()
