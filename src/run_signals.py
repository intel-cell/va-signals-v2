#!/usr/bin/env python
"""
CLI runner for Signals Routing.

Usage:
    python -m src.run_signals route                    # Route pending events
    python -m src.run_signals route --dry-run          # Route without writing output
    python -m src.run_signals route --source hearings  # Route only hearings
    python -m src.run_signals status                   # Show system status
    python -m src.run_signals test-envelope            # Test with sample envelope
"""

# Allow running as a script (python src/run_signals.py) by setting package context
if __name__ == "__main__" and __package__ is None:
    import sys

    sys.path.append(str(__import__("pathlib").Path(__file__).resolve().parent.parent))
    __package__ = "src"

import argparse
import logging
from pathlib import Path

from .db import connect, execute, init_db, insert_source_run
from .provenance import utc_now_iso
from .signals.adapters import BillsAdapter, HearingsAdapter, OMEventsAdapter
from .signals.envelope import Envelope
from .signals.output.audit_log import write_audit_log
from .signals.router import RouteResult, SignalsRouter
from .signals.schema.loader import get_routing_rule

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _get_available_categories() -> list[str]:
    """Get list of available category schema files."""
    config_dir = Path(__file__).resolve().parents[1] / "config" / "signals"
    if not config_dir.exists():
        return []
    return [p.stem for p in config_dir.glob("*.yaml")]


def _fetch_unrouted_hearings(limit: int = 100) -> list[dict]:
    """Fetch hearings that haven't been routed yet."""
    con = connect()
    try:
        # Get hearings not in audit log
        cur = execute(
            con,
            """SELECT h.event_id, h.congress, h.chamber, h.committee_code, h.committee_name,
                      h.hearing_date, h.hearing_time, h.title, h.meeting_type, h.status,
                      h.location, h.url, h.first_seen_at, h.updated_at
               FROM hearings h
               WHERE NOT EXISTS (
                   SELECT 1 FROM signal_audit_log a WHERE a.authority_id = h.event_id
               )
               ORDER BY h.first_seen_at DESC
               LIMIT :limit""",
            {"limit": limit},
        )
        rows = cur.fetchall()
        return [
            {
                "event_id": r[0],
                "congress": r[1],
                "chamber": r[2],
                "committee_code": r[3],
                "committee_name": r[4],
                "hearing_date": r[5],
                "hearing_time": r[6],
                "title": r[7],
                "meeting_type": r[8],
                "status": r[9],
                "location": r[10],
                "url": r[11],
                "first_seen_at": r[12],
                "updated_at": r[13],
            }
            for r in rows
        ]
    finally:
        con.close()


def _fetch_unrouted_bills(limit: int = 100) -> list[dict]:
    """Fetch bills that haven't been routed yet."""
    con = connect()
    try:
        cur = execute(
            con,
            """SELECT b.bill_id, b.congress, b.bill_type, b.bill_number, b.title,
                      b.sponsor_name, b.sponsor_party, b.introduced_date,
                      b.latest_action_date, b.latest_action_text, b.policy_area,
                      b.committees_json, b.cosponsors_count, b.first_seen_at, b.updated_at
               FROM bills b
               WHERE NOT EXISTS (
                   SELECT 1 FROM signal_audit_log a WHERE a.authority_id = b.bill_id
               )
               ORDER BY b.first_seen_at DESC
               LIMIT :limit""",
            {"limit": limit},
        )
        rows = cur.fetchall()
        return [
            {
                "bill_id": r[0],
                "congress": r[1],
                "bill_type": r[2],
                "bill_number": r[3],
                "title": r[4],
                "sponsor_name": r[5],
                "sponsor_party": r[6],
                "introduced_date": r[7],
                "latest_action_date": r[8],
                "latest_action_text": r[9],
                "policy_area": r[10],
                "committees_json": r[11],
                "cosponsors_count": r[12],
                "first_seen_at": r[13],
                "updated_at": r[14],
            }
            for r in rows
        ]
    finally:
        con.close()


def _fetch_unrouted_om_events(limit: int = 100) -> list[dict]:
    """Fetch oversight monitor events that haven't been routed yet."""
    con = connect()
    try:
        cur = execute(
            con,
            """SELECT e.event_id, e.event_type, e.theme, e.primary_source_type,
                      e.primary_url, e.pub_timestamp, e.pub_precision, e.title,
                      e.summary, e.raw_content, e.is_escalation, e.escalation_signals,
                      e.is_deviation, e.deviation_reason, e.fetched_at
               FROM om_events e
               WHERE NOT EXISTS (
                   SELECT 1 FROM signal_audit_log a WHERE a.authority_id = e.event_id
               )
               ORDER BY e.fetched_at DESC
               LIMIT :limit""",
            {"limit": limit},
        )
        rows = cur.fetchall()
        return [
            {
                "event_id": r[0],
                "event_type": r[1],
                "theme": r[2],
                "primary_source_type": r[3],
                "primary_url": r[4],
                "pub_timestamp": r[5],
                "pub_precision": r[6],
                "title": r[7],
                "summary": r[8],
                "raw_content": r[9],
                "is_escalation": r[10],
                "escalation_signals": r[11],
                "is_deviation": r[12],
                "deviation_reason": r[13],
                "fetched_at": r[14],
            }
            for r in rows
        ]
    finally:
        con.close()


def _process_route_result(
    router: SignalsRouter,
    envelope: Envelope,
    result: RouteResult,
    routing_rule: dict,
) -> None:
    """Process a single route result - write audit log and send alerts."""
    # Write audit log
    write_audit_log(
        event_id=envelope.event_id,
        authority_id=envelope.authority_id,
        indicator_id=result.indicator_id,
        trigger_id=result.trigger_id,
        severity=result.severity,
        result=result.evaluation,
        suppressed=result.suppressed,
        suppression_reason=result.suppression_reason,
    )
    # Record fire for suppression (only for non-suppressed results)
    if not result.suppressed:
        cooldown_minutes = routing_rule.get("suppression", {}).get("cooldown_minutes", 60)
        router.suppression.record_fire(
            trigger_id=result.trigger_id,
            authority_id=envelope.authority_id,
            version=envelope.version,
            cooldown_minutes=cooldown_minutes,
        )
    # Log alert action (email notifications handled via daily digest)
    if "post_slack_alert" in result.actions:
        logger.info(
            f"Signal fired: {result.trigger_id} for {envelope.authority_id} "
            f"(severity={result.severity})"
        )


def _get_routing_rule_for_result(router: SignalsRouter, result: RouteResult) -> dict:
    """Look up the routing rule for a route result from the loaded schemas."""
    for schema in router.schemas.values():
        rule = get_routing_rule(schema, result.trigger_id)
        if rule:
            return rule
    return {}


def cmd_route(args):
    """Route pending events through the signals engine."""
    init_db()
    started_at = utc_now_iso()
    errors: list[str] = []
    status = "SUCCESS"

    categories = _get_available_categories()
    if not categories:
        print("No signal categories found in config/signals/")
        return

    router = SignalsRouter(categories=categories)

    # Adapters
    hearings_adapter = HearingsAdapter()
    bills_adapter = BillsAdapter()
    om_adapter = OMEventsAdapter()

    # Stats
    total_events = 0
    total_matches = 0
    total_suppressed = 0
    limit = args.limit or 100
    source_filter = args.source
    dry_run = args.dry_run

    try:
        # Route hearings
        if source_filter is None or source_filter == "hearings":
            hearings = _fetch_unrouted_hearings(limit=limit)
            for hearing in hearings:
                total_events += 1
                envelope = hearings_adapter.adapt(hearing)
                results = router.route(envelope)

                for result in results:
                    if result.suppressed:
                        total_suppressed += 1
                    else:
                        total_matches += 1
                        if not dry_run:
                            routing_rule = _get_routing_rule_for_result(router, result)
                            _process_route_result(router, envelope, result, routing_rule)

        # Route bills
        if source_filter is None or source_filter == "bills":
            bills = _fetch_unrouted_bills(limit=limit)
            for bill in bills:
                total_events += 1
                envelope = bills_adapter.adapt(bill)
                results = router.route(envelope)

                for result in results:
                    if result.suppressed:
                        total_suppressed += 1
                    else:
                        total_matches += 1
                        if not dry_run:
                            routing_rule = _get_routing_rule_for_result(router, result)
                            _process_route_result(router, envelope, result, routing_rule)

        # Route OM events
        if source_filter is None or source_filter == "om_events":
            om_events = _fetch_unrouted_om_events(limit=limit)
            for om_event in om_events:
                total_events += 1
                envelope = om_adapter.adapt(om_event)
                results = router.route(envelope)

                for result in results:
                    if result.suppressed:
                        total_suppressed += 1
                    else:
                        total_matches += 1
                        if not dry_run:
                            routing_rule = _get_routing_rule_for_result(router, result)
                            _process_route_result(router, envelope, result, routing_rule)

    except Exception as e:
        status = "ERROR"
        errors.append(f"EXCEPTION: {repr(e)}")
        logger.exception("Error during routing")

    # Determine final status
    ended_at = utc_now_iso()
    if status == "SUCCESS":
        status = "NO_DATA" if total_events == 0 else "SUCCESS"

    # Record source run (unless dry run)
    if not dry_run:
        run_record = {
            "source_id": "signals_routing",
            "started_at": started_at,
            "ended_at": ended_at,
            "status": status,
            "records_fetched": total_events,
            "errors": errors,
        }
        insert_source_run(run_record)

    # Print summary
    mode = "(dry run)" if dry_run else ""
    print(f"\n=== Signals Routing Complete {mode} ===")
    print(f"Events processed: {total_events}")
    print(f"Triggers matched: {total_matches}")
    print(f"Triggers suppressed: {total_suppressed}")


def cmd_status(args):
    """Show signals system status."""
    init_db()

    print("\n=== Signals System Status ===")

    # Categories
    categories = _get_available_categories()
    print(f"\nLoaded Categories: {len(categories)}")
    for cat in categories:
        print(f"  - {cat}")

    # Recent fires from audit log
    con = connect()
    cur = execute(
        con,
        """SELECT trigger_id, severity, authority_id, fired_at, suppressed
           FROM signal_audit_log
           ORDER BY fired_at DESC
           LIMIT 10""",
    )
    recent_fires = cur.fetchall()

    print(f"\nRecent Trigger Fires: {len(recent_fires)}")
    for trigger_id, severity, authority_id, fired_at, suppressed in recent_fires:
        supp_mark = " (suppressed)" if suppressed else ""
        print(
            f"  [{severity.upper()}] {trigger_id} - {authority_id[:30]} @ {fired_at[:19]}{supp_mark}"
        )

    # Counts by severity
    cur = execute(
        con,
        """SELECT severity, COUNT(*) FROM signal_audit_log
           WHERE suppressed = 0
           GROUP BY severity""",
    )
    by_severity = dict(cur.fetchall())

    print("\nFires by Severity:")
    for sev in ["critical", "high", "medium", "low"]:
        count = by_severity.get(sev, 0)
        if count > 0:
            print(f"  {sev}: {count}")

    # Active suppressions
    cur = execute(
        con,
        """SELECT trigger_id, authority_id, cooldown_until
           FROM signal_suppression
           WHERE cooldown_until > :now
           ORDER BY cooldown_until DESC
           LIMIT 10""",
        {"now": utc_now_iso()},
    )
    active_suppressions = cur.fetchall()

    print(f"\nActive Suppressions: {len(active_suppressions)}")
    for trigger_id, authority_id, cooldown_until in active_suppressions:
        print(f"  {trigger_id} - {authority_id[:30]} until {cooldown_until[:19]}")

    con.close()


def cmd_test_envelope(args):
    """Test routing with a sample GAO-related envelope."""
    init_db()

    print("\n=== Test Envelope Routing (Dry Run) ===")

    # Create a test envelope that should match oversight_accountability
    test_envelope = Envelope(
        event_id="test-envelope-001",
        authority_id="TEST-AUTH-001",
        authority_source="congress_gov",
        authority_type="hearing_notice",
        title="Hearing on GAO Report: VA Disability Claims Processing",
        body_text="""The House Committee on Veterans' Affairs will hold a hearing to examine
        the findings of the Government Accountability Office (GAO) investigation into
        VA disability claims processing. The GAO audit found significant issues with
        contractor exam quality and claims backlog management.""",
        committee="HVAC",
        topics=["disability_benefits", "claims_backlog", "exam_quality"],
        version=1,
        published_at="2026-01-21T10:00:00Z",
        source_url="https://veterans.house.gov/hearings/test-hearing",
    )

    print("\nTest Envelope:")
    print(f"  Event ID: {test_envelope.event_id}")
    print(f"  Authority: {test_envelope.authority_source} / {test_envelope.authority_type}")
    print(f"  Title: {test_envelope.title}")
    print(f"  Committee: {test_envelope.committee}")
    print(f"  Topics: {', '.join(test_envelope.topics)}")

    # Route through the system
    categories = _get_available_categories()
    if not categories:
        print("\nNo signal categories found in config/signals/")
        return

    router = SignalsRouter(categories=categories)
    results = router.route(test_envelope)

    print("\n--- Routing Results ---")
    print(f"Total triggers matched: {len(results)}")

    for result in results:
        print(f"\n  Trigger: {result.trigger_id}")
        print(f"    Indicator: {result.indicator_id}")
        print(f"    Severity: {result.severity}")
        print(f"    Actions: {', '.join(result.actions)}")
        print(f"    Human review: {'Yes' if result.human_review_required else 'No'}")
        print(f"    Suppressed: {'Yes' if result.suppressed else 'No'}")
        if result.suppression_reason:
            print(f"    Suppression reason: {result.suppression_reason}")

        # Show evaluation details
        if result.evaluation:
            if result.evaluation.matched_terms:
                print(f"    Matched terms: {', '.join(result.evaluation.matched_terms[:5])}")
            if result.evaluation.matched_discriminators:
                print(
                    f"    Discriminators: {', '.join(result.evaluation.matched_discriminators[:3])}"
                )

    if not results:
        print("\n  No triggers matched for this envelope.")

    print("\n(No audit log written - this is a dry run)")


def main():
    parser = argparse.ArgumentParser(description="Signals Routing CLI")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Route command
    route_parser = subparsers.add_parser("route", help="Route pending events")
    route_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Process events without writing to audit log or sending alerts",
    )
    route_parser.add_argument(
        "--source",
        choices=["hearings", "bills", "om_events"],
        help="Route only events from this source",
    )
    route_parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum events to process per source (default: 100)",
    )

    # Status command
    subparsers.add_parser("status", help="Show signals system status")

    # Test-envelope command
    subparsers.add_parser("test-envelope", help="Test routing with a sample envelope")

    args = parser.parse_args()

    if args.command == "route":
        cmd_route(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "test-envelope":
        cmd_test_envelope(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
