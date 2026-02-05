"""
Gate Detection System

Detects changes in decision points and creates alerts:
- New hearing scheduled
- Markup date announced/changed
- Comment deadline extended/shortened
- Rule effective date changed
- Bill status changed
- Amendment filed on tracked vehicle
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from ..db import connect, execute as db_execute
from .db_helpers import (
    create_gate_alert,
    get_vehicle,
    get_calendar_events,
)

logger = logging.getLogger(__name__)


def _execute(sql: str, params: dict | None = None) -> list[dict]:
    """Execute a query and return results as list of dicts."""
    conn = connect()
    conn.row_factory = lambda cursor, row: dict(
        (col[0], row[idx]) for idx, col in enumerate(cursor.description)
    ) if cursor.description else {}
    cursor = db_execute(conn, sql, params)
    try:
        results = cursor.fetchall()
    except Exception:
        results = []
    return results


def _execute_write(sql: str, params: dict | None = None) -> None:
    """Execute a write query."""
    conn = connect()
    db_execute(conn, sql, params)
    conn.commit()


def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse a date string to datetime."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def _days_between(old_date: str, new_date: str) -> Optional[int]:
    """Calculate days between two dates. Positive = delayed, Negative = accelerated."""
    old = _parse_date(old_date)
    new = _parse_date(new_date)
    if old and new:
        return (new - old).days
    return None


def detect_hearing_changes() -> dict:
    """
    Detect changes in hearing schedules.

    Uses hearing_updates table to find recent changes.
    Creates alerts for:
    - New hearings scheduled
    - Hearing date changed
    - Hearing status changed (e.g., Scheduled -> Cancelled)

    Returns: {new_hearings: int, date_changes: int, status_changes: int, alerts_created: int}
    """
    stats = {"new_hearings": 0, "date_changes": 0, "status_changes": 0, "alerts_created": 0}

    # Check for hearing updates in last 24 hours
    cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()

    # Get hearing updates
    updates = _execute(
        """
        SELECT hu.id, hu.event_id, hu.field_changed, hu.old_value, hu.new_value, hu.detected_at,
               h.title, h.hearing_date, h.status
        FROM hearing_updates hu
        JOIN hearings h ON hu.event_id = h.event_id
        WHERE hu.detected_at >= :cutoff
        ORDER BY hu.detected_at DESC
        """,
        {"cutoff": cutoff},
    )

    for update in updates:
        vehicle_id = f"hearing_{update['event_id']}"

        if update["field_changed"] == "hearing_date":
            # Date change
            days_impact = _days_between(update["old_value"], update["new_value"])

            create_gate_alert(
                vehicle_id=vehicle_id,
                alert_type="gate_moved",
                old_value=update["old_value"],
                new_value=update["new_value"],
                days_impact=days_impact,
                recommended_action=_recommend_date_action(days_impact),
                source_event_id=str(update["id"]),
                source_type="hearing_updates",
            )
            stats["date_changes"] += 1
            stats["alerts_created"] += 1
            logger.info(f"Gate moved alert: Hearing {update['event_id']} date changed by {days_impact} days")

        elif update["field_changed"] == "status":
            # Status change (e.g., Scheduled -> Cancelled)
            create_gate_alert(
                vehicle_id=vehicle_id,
                alert_type="status_changed",
                old_value=update["old_value"],
                new_value=update["new_value"],
                recommended_action=_recommend_status_action(update["old_value"], update["new_value"]),
                source_event_id=str(update["id"]),
                source_type="hearing_updates",
            )
            stats["status_changes"] += 1
            stats["alerts_created"] += 1
            logger.info(f"Status change alert: Hearing {update['event_id']} {update['old_value']} -> {update['new_value']}")

    # Check for newly added hearings (first_seen_at in last 24 hours)
    new_hearings = _execute(
        """
        SELECT event_id, title, hearing_date, committee_name
        FROM hearings
        WHERE first_seen_at >= :cutoff
          AND hearing_date >= date('now')
        ORDER BY first_seen_at DESC
        """,
        {"cutoff": cutoff},
    )

    for hearing in new_hearings:
        vehicle_id = f"hearing_{hearing['event_id']}"

        create_gate_alert(
            vehicle_id=vehicle_id,
            alert_type="new_gate",
            new_value=f"Hearing scheduled for {hearing['hearing_date']}",
            recommended_action="Review hearing agenda and prepare talking points",
            source_event_id=hearing["event_id"],
            source_type="hearings",
        )
        stats["new_hearings"] += 1
        stats["alerts_created"] += 1
        logger.info(f"New gate alert: Hearing {hearing['event_id']} scheduled for {hearing['hearing_date']}")

    logger.info(f"Hearing detection complete: {stats}")
    return stats


def detect_bill_status_changes() -> dict:
    """
    Detect changes in bill status.

    Uses bill_actions table to find recent actions.
    Creates alerts for significant status changes.

    Returns: {status_changes: int, alerts_created: int}
    """
    stats = {"status_changes": 0, "alerts_created": 0}

    # Check for new bill actions in last 24 hours
    cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()

    # Get recent bill actions that indicate status changes
    actions = _execute(
        """
        SELECT ba.id, ba.bill_id, ba.action_date, ba.action_text, ba.action_type,
               b.title, b.bill_type, b.bill_number
        FROM bill_actions ba
        JOIN bills b ON ba.bill_id = b.bill_id
        WHERE ba.first_seen_at >= :cutoff
        ORDER BY ba.action_date DESC
        """,
        {"cutoff": cutoff},
    )

    # Keywords that indicate significant status changes
    significant_keywords = [
        "passed",
        "ordered to be reported",
        "reported by",
        "markup",
        "amendment",
        "conference",
        "signed by",
        "became public law",
        "veto",
        "floor consideration",
    ]

    for action in actions:
        action_text = (action["action_text"] or "").lower()

        # Check if this is a significant action
        is_significant = any(kw in action_text for kw in significant_keywords)

        if is_significant:
            vehicle_id = f"bill_{action['bill_id']}"
            identifier = f"{action['bill_type'].upper()} {action['bill_number']}"

            # Determine alert type and recommendation
            alert_type = "status_changed"
            if "amendment" in action_text:
                alert_type = "status_changed"  # Could be separate "amendment" type
                recommendation = "Review amendment text and assess impact"
            elif "passed" in action_text:
                recommendation = "Update stakeholders on passage; prepare for next chamber"
            elif "markup" in action_text or "ordered to be reported" in action_text:
                recommendation = "Bill advancing - review committee report when available"
            elif "signed" in action_text or "public law" in action_text:
                recommendation = "Bill enacted - prepare implementation analysis"
            else:
                recommendation = "Review action and assess implications"

            create_gate_alert(
                vehicle_id=vehicle_id,
                alert_type=alert_type,
                new_value=action["action_text"],
                recommended_action=recommendation,
                source_event_id=str(action["id"]),
                source_type="bill_actions",
            )
            stats["status_changes"] += 1
            stats["alerts_created"] += 1
            logger.info(f"Bill status alert: {identifier} - {action['action_text'][:50]}")

    logger.info(f"Bill status detection complete: {stats}")
    return stats


def detect_oversight_escalations() -> dict:
    """
    Detect new escalations and deviations in oversight events.

    Returns: {escalations: int, deviations: int, alerts_created: int}
    """
    stats = {"escalations": 0, "deviations": 0, "alerts_created": 0}

    # Check for new escalations in last 24 hours
    cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()

    escalations = _execute(
        """
        SELECT event_id, title, primary_source_type, pub_timestamp,
               is_escalation, is_deviation, escalation_signals, deviation_reason
        FROM om_events
        WHERE created_at >= :cutoff
          AND (is_escalation = 1 OR is_deviation = 1)
        ORDER BY pub_timestamp DESC
        """,
        {"cutoff": cutoff},
    )

    for event in escalations:
        vehicle_id = f"om_{event['event_id']}"

        if event["is_escalation"]:
            create_gate_alert(
                vehicle_id=vehicle_id,
                alert_type="new_gate",
                new_value=f"Escalation: {event['title'][:100]}",
                recommended_action="Review escalation and brief leadership",
                source_event_id=event["event_id"],
                source_type="om_events",
            )
            stats["escalations"] += 1
            stats["alerts_created"] += 1

        if event["is_deviation"]:
            create_gate_alert(
                vehicle_id=vehicle_id,
                alert_type="status_changed",
                new_value=f"Deviation detected: {event['deviation_reason'] or 'Review required'}",
                recommended_action="Analyze deviation from baseline",
                source_event_id=event["event_id"],
                source_type="om_events",
            )
            stats["deviations"] += 1
            stats["alerts_created"] += 1

    logger.info(f"Oversight detection complete: {stats}")
    return stats


def detect_passed_gates() -> dict:
    """
    Mark calendar events as passed when their date has elapsed.

    Returns: {marked_passed: int}
    """
    stats = {"marked_passed": 0}

    today = datetime.utcnow().date().isoformat()

    # Find events that should be marked as passed
    passed_events = _execute(
        """
        SELECT event_id, vehicle_id, date, title
        FROM bf_calendar_events
        WHERE date < :today
          AND passed = 0
          AND cancelled = 0
        """,
        {"today": today},
    )

    for event in passed_events:
        # Mark as passed
        _execute_write(
            "UPDATE bf_calendar_events SET passed = 1, updated_at = :now WHERE event_id = :event_id",
            {"event_id": event["event_id"], "now": datetime.utcnow().isoformat()},
        )

        # Create gate_passed alert
        create_gate_alert(
            vehicle_id=event["vehicle_id"],
            alert_type="gate_passed",
            new_value=f"Gate passed: {event['title'][:100]}",
            recommended_action="Review outcomes and update vehicle status",
            source_event_id=event["event_id"],
            source_type="bf_calendar_events",
        )

        stats["marked_passed"] += 1
        logger.debug(f"Marked gate as passed: {event['event_id']}")

    logger.info(f"Passed gate detection complete: {stats}")
    return stats


def _recommend_date_action(days_impact: Optional[int]) -> str:
    """Generate recommendation based on date change impact."""
    if days_impact is None:
        return "Review date change and update tracking"

    if days_impact > 14:
        return "Significant delay - reassess timeline and resource allocation"
    elif days_impact > 7:
        return "Moderate delay - adjust preparation schedule"
    elif days_impact > 0:
        return "Minor delay - update calendar"
    elif days_impact < -7:
        return "ACCELERATED - prioritize preparation immediately"
    elif days_impact < 0:
        return "Accelerated timeline - verify preparation status"
    else:
        return "No change in timing"


def _recommend_status_action(old_status: Optional[str], new_status: str) -> str:
    """Generate recommendation based on status change."""
    new_lower = new_status.lower()

    if "cancel" in new_lower:
        return "Event cancelled - reallocate resources; monitor for rescheduling"
    elif "postpone" in new_lower:
        return "Event postponed - monitor for new date announcement"
    elif "reschedul" in new_lower:
        return "Event rescheduled - verify new date and update calendar"
    elif "scheduled" in new_lower:
        return "Event now scheduled - begin preparation"
    else:
        return "Status changed - review implications"


def run_all_detections() -> dict:
    """
    Run all gate detection checks.

    Returns: Combined statistics from all detections.
    """
    logger.info("Starting full gate detection run...")

    results = {
        "hearings": detect_hearing_changes(),
        "bills": detect_bill_status_changes(),
        "oversight": detect_oversight_escalations(),
        "passed_gates": detect_passed_gates(),
    }

    total_alerts = sum(r.get("alerts_created", 0) for r in results.values())
    logger.info(f"Full gate detection complete: {total_alerts} alerts created")

    return results
