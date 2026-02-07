"""
Calendar Aggregator

Extracts decision point dates from all sources and populates the battlefield calendar.
Sources:
- Hearings: hearing_date field
- Bills: status changes indicate movement (introduced_date, latest_action_date)
- Federal Register: comments_close_date, effective_date (when available)
- Oversight Events: pub_timestamp, event_timestamp
"""

import logging
from datetime import datetime, timedelta

from ..db import connect
from ..db import execute as db_execute
from .db_helpers import (
    upsert_calendar_event,
    upsert_vehicle,
)

logger = logging.getLogger(__name__)


def _execute(sql: str, params: dict | None = None) -> list[dict]:
    """Execute a query and return results as list of dicts."""
    conn = connect()
    conn.row_factory = lambda cursor, row: (
        {col[0]: row[idx] for idx, col in enumerate(cursor.description)}
        if cursor.description
        else {}
    )
    cursor = db_execute(conn, sql, params)
    try:
        results = cursor.fetchall()
    except Exception:
        results = []
    return results


def _days_until(date_str: str) -> int:
    """Calculate days until a date from today."""
    try:
        target = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        today = datetime.utcnow().date()
        return (target - today).days
    except (ValueError, TypeError):
        return 999


def _determine_importance(event_type: str, days_until: int, status: str | None = None) -> str:
    """Determine importance level based on event type and timing."""
    # Critical: any event within 7 days
    if days_until <= 7:
        return "critical"

    # Important: hearings, markups, votes within 14 days
    if days_until <= 14 and event_type in ("hearing", "markup", "vote", "floor_action"):
        return "important"

    # Important: comment deadlines within 30 days
    if days_until <= 30 and event_type == "comment_deadline":
        return "important"

    # Important: effective dates within 60 days (need compliance prep time)
    if days_until <= 60 and event_type == "effective_date":
        return "important"

    return "watch"


def sync_hearings_to_calendar() -> dict:
    """
    Sync hearings to battlefield vehicles and calendar.

    Returns: {created_vehicles: int, created_events: int, updated_events: int}
    """
    stats = {"created_vehicles": 0, "created_events": 0, "updated_events": 0}

    # Get upcoming hearings (next 90 days)
    today = datetime.utcnow().date().isoformat()
    (datetime.utcnow().date() + timedelta(days=90)).isoformat()

    rows = _execute(
        """
        SELECT event_id, congress, chamber, committee_code, committee_name,
               hearing_date, hearing_time, title, meeting_type, status, location, url
        FROM hearings
        WHERE hearing_date >= :today
          AND status NOT IN ('Cancelled', 'Postponed')
        ORDER BY hearing_date ASC
        """,
        {"today": today},
    )

    for row in rows:
        hearing_date = row["hearing_date"]
        days = _days_until(hearing_date)

        # Skip if too far out
        if days > 90:
            continue

        # Create or update vehicle
        vehicle_id = f"hearing_{row['event_id']}"
        identifier = f"{row['chamber']}-{row['committee_code']}-{row['event_id']}"

        upsert_vehicle(
            vehicle_id=vehicle_id,
            vehicle_type="oversight",  # Hearings are oversight vehicles
            title=row["title"][:200] if row["title"] else "Untitled Hearing",
            identifier=identifier,
            current_stage="committee",
            status_date=hearing_date,
            status_text=row["status"],
            source_type="hearings",
            source_id=row["event_id"],
            source_url=row["url"],
        )
        stats["created_vehicles"] += 1

        # Create calendar event
        event_id = f"evt_hearing_{row['event_id']}"
        importance = _determine_importance("hearing", days, row["status"])

        upsert_calendar_event(
            event_id=event_id,
            vehicle_id=vehicle_id,
            date=hearing_date,
            event_type="hearing",
            title=row["title"][:200] if row["title"] else "Hearing",
            time=row["hearing_time"],
            location=row["location"] or row["committee_name"],
            importance=importance,
            source_type="hearings",
            source_id=row["event_id"],
        )
        stats["created_events"] += 1

    logger.info(f"Synced hearings to calendar: {stats}")
    return stats


def sync_bills_to_calendar() -> dict:
    """
    Sync VA bills to battlefield vehicles.
    Creates calendar events for significant bill actions.

    Returns: {created_vehicles: int, created_events: int}
    """
    stats = {"created_vehicles": 0, "created_events": 0}

    # Get active bills (with recent action in last 90 days)
    cutoff = (datetime.utcnow().date() - timedelta(days=90)).isoformat()

    rows = _execute(
        """
        SELECT bill_id, congress, bill_type, bill_number, title,
               sponsor_name, sponsor_party, introduced_date,
               latest_action_date, latest_action_text, policy_area,
               cosponsors_count
        FROM bills
        WHERE latest_action_date >= :cutoff
        ORDER BY latest_action_date DESC
        """,
        {"cutoff": cutoff},
    )

    for row in rows:
        # Determine stage from latest action text
        action_text = (row["latest_action_text"] or "").lower()
        stage = "introduced"

        if "committee" in action_text or "referred" in action_text:
            stage = "committee"
        elif "markup" in action_text or "ordered to be reported" in action_text:
            stage = "markup"
        elif "passed" in action_text and "house" in action_text:
            stage = "floor"
        elif "passed" in action_text and "senate" in action_text:
            stage = "floor"
        elif "conference" in action_text:
            stage = "conference"
        elif "became public law" in action_text or "signed by president" in action_text:
            stage = "enacted"

        # Create identifier
        bill_type = row["bill_type"].upper()
        identifier = f"{bill_type} {row['bill_number']}"

        vehicle_id = f"bill_{row['bill_id']}"
        upsert_vehicle(
            vehicle_id=vehicle_id,
            vehicle_type="bill",
            title=row["title"][:200] if row["title"] else identifier,
            identifier=identifier,
            current_stage=stage,
            status_date=row["latest_action_date"],
            status_text=row["latest_action_text"],
            last_action=row["latest_action_text"],
            last_action_date=row["latest_action_date"],
            source_type="bills",
            source_id=row["bill_id"],
        )
        stats["created_vehicles"] += 1

        # Create calendar event for latest action if recent
        if row["latest_action_date"]:
            days = _days_until(row["latest_action_date"])
            if -7 <= days <= 0:  # Recent past action (last 7 days)
                event_id = f"evt_bill_{row['bill_id']}_{row['latest_action_date']}"
                importance = "important" if stage in ("markup", "floor", "enacted") else "watch"

                upsert_calendar_event(
                    event_id=event_id,
                    vehicle_id=vehicle_id,
                    date=row["latest_action_date"],
                    event_type="floor_action" if stage == "floor" else "amendment",
                    title=f"{identifier}: {row['latest_action_text'][:100]}"
                    if row["latest_action_text"]
                    else identifier,
                    importance=importance,
                    source_type="bills",
                    source_id=row["bill_id"],
                )
                stats["created_events"] += 1

    logger.info(f"Synced bills to calendar: {stats}")
    return stats


def sync_federal_register_to_calendar() -> dict:
    """
    Sync Federal Register documents to battlefield vehicles and calendar events.

    Creates calendar events for:
    - Comment deadlines (comments_close_date)
    - Effective dates (effective_date)

    Returns: {created_vehicles: int, created_events: int, skipped_no_dates: int}
    """
    stats = {"created_vehicles": 0, "created_events": 0, "skipped_no_dates": 0}

    # Get recent FR documents with summaries (indicating VA relevance)
    cutoff = (datetime.utcnow().date() - timedelta(days=30)).isoformat()

    rows = _execute(
        """
        SELECT f.doc_id, f.published_date, f.source_url,
               f.comments_close_date, f.effective_date, f.document_type, f.title,
               s.summary, s.veteran_impact, s.tags
        FROM fr_seen f
        LEFT JOIN fr_summaries s ON f.doc_id = s.doc_id
        WHERE f.published_date >= :cutoff
          AND s.doc_id IS NOT NULL
        ORDER BY f.published_date DESC
        """,
        {"cutoff": cutoff},
    )

    for row in rows:
        vehicle_id = f"fr_{row['doc_id']}"

        # Determine stage from document_type or tags/summary
        doc_type = (row.get("document_type") or "").lower()
        tags = row["tags"] or ""
        summary = row["summary"] or ""

        if (
            "proposed" in doc_type
            or "proposed rule" in tags.lower()
            or "proposed rule" in summary.lower()
        ):
            stage = "proposed_rule"
            vehicle_type = "rule"
        elif "final" in doc_type or "final rule" in tags.lower() or "final rule" in summary.lower():
            stage = "final_rule"
            vehicle_type = "rule"
        else:
            stage = "active"
            vehicle_type = "rule"

        # Use title from FR API if available, fallback to summary
        title = row.get("title") or row["summary"] or f"FR Doc {row['doc_id']}"

        upsert_vehicle(
            vehicle_id=vehicle_id,
            vehicle_type=vehicle_type,
            title=title[:200],
            identifier=row["doc_id"],
            current_stage=stage,
            status_date=row["published_date"],
            status_text=row["veteran_impact"],
            source_type="fr_seen",
            source_id=row["doc_id"],
            source_url=row["source_url"],
        )
        stats["created_vehicles"] += 1

        # Create calendar events for comment deadlines
        comments_close = row.get("comments_close_date")
        if comments_close:
            days = _days_until(comments_close)
            if days >= 0:  # Only future deadlines
                event_id = f"evt_fr_comment_{row['doc_id']}"
                importance = _determine_importance("comment_deadline", days)

                upsert_calendar_event(
                    event_id=event_id,
                    vehicle_id=vehicle_id,
                    date=comments_close,
                    event_type="comment_deadline",
                    title=f"Comment Deadline: {title[:150]}",
                    importance=importance,
                    prep_required="Submit public comments before deadline",
                    source_type="fr_seen",
                    source_id=row["doc_id"],
                )
                stats["created_events"] += 1

        # Create calendar events for effective dates
        effective = row.get("effective_date")
        if effective:
            days = _days_until(effective)
            if days >= 0:  # Only future effective dates
                event_id = f"evt_fr_effective_{row['doc_id']}"
                importance = _determine_importance("effective_date", days)

                upsert_calendar_event(
                    event_id=event_id,
                    vehicle_id=vehicle_id,
                    date=effective,
                    event_type="effective_date",
                    title=f"Effective Date: {title[:150]}",
                    importance=importance,
                    prep_required="Ensure compliance readiness",
                    source_type="fr_seen",
                    source_id=row["doc_id"],
                )
                stats["created_events"] += 1

        # Track if we skipped due to no dates
        if not comments_close and not effective:
            stats["skipped_no_dates"] += 1

    logger.info(f"Synced Federal Register to calendar: {stats}")
    return stats


def sync_oversight_to_calendar() -> dict:
    """
    Sync oversight monitor events to battlefield vehicles.

    Returns: {created_vehicles: int, created_events: int}
    """
    stats = {"created_vehicles": 0, "created_events": 0}

    # Get recent oversight events (last 30 days)
    cutoff = (datetime.utcnow() - timedelta(days=30)).isoformat()

    rows = _execute(
        """
        SELECT event_id, event_type, theme, primary_source_type, primary_url,
               pub_timestamp, title, summary, is_escalation, is_deviation
        FROM om_events
        WHERE pub_timestamp >= :cutoff
          AND surfaced = 1
        ORDER BY pub_timestamp DESC
        """,
        {"cutoff": cutoff},
    )

    for row in rows:
        vehicle_id = f"om_{row['event_id']}"

        # Determine posture based on escalation/deviation
        posture = "monitor"
        if row["is_escalation"]:
            posture = "neutral_engaged"

        upsert_vehicle(
            vehicle_id=vehicle_id,
            vehicle_type="oversight",
            title=row["title"][:200] if row["title"] else "Oversight Event",
            identifier=row["event_id"],
            current_stage="active",
            status_date=row["pub_timestamp"][:10]
            if row["pub_timestamp"]
            else datetime.utcnow().date().isoformat(),
            status_text=row["summary"][:200] if row["summary"] else None,
            our_posture=posture,
            source_type="om_events",
            source_id=row["event_id"],
            source_url=row["primary_url"],
        )
        stats["created_vehicles"] += 1

        # Create calendar event for escalations
        if row["is_escalation"] or row["is_deviation"]:
            pub_date = (
                row["pub_timestamp"][:10]
                if row["pub_timestamp"]
                else datetime.utcnow().date().isoformat()
            )
            event_id = f"evt_om_{row['event_id']}"

            upsert_calendar_event(
                event_id=event_id,
                vehicle_id=vehicle_id,
                date=pub_date,
                event_type="hearing"
                if "hearing" in (row["event_type"] or "").lower()
                else "amendment",
                title=row["title"][:200] if row["title"] else "Oversight Event",
                importance="important" if row["is_escalation"] else "watch",
                source_type="om_events",
                source_id=row["event_id"],
            )
            stats["created_events"] += 1

    logger.info(f"Synced oversight events to calendar: {stats}")
    return stats


def sync_all_sources() -> dict:
    """
    Run full calendar sync from all sources.

    Returns: Combined statistics from all syncs.
    """
    logger.info("Starting full calendar sync...")

    results = {
        "hearings": sync_hearings_to_calendar(),
        "bills": sync_bills_to_calendar(),
        "federal_register": sync_federal_register_to_calendar(),
        "oversight": sync_oversight_to_calendar(),
    }

    total_vehicles = sum(r.get("created_vehicles", 0) for r in results.values())
    total_events = sum(r.get("created_events", 0) for r in results.values())

    logger.info(f"Full calendar sync complete: {total_vehicles} vehicles, {total_events} events")
    return results


def get_calendar_view(days: int = 14) -> list[dict]:
    """
    Get calendar view for the next N days with vehicle context.

    Returns events enriched with vehicle data.
    """
    today = datetime.utcnow().date().isoformat()
    end_date = (datetime.utcnow().date() + timedelta(days=days)).isoformat()

    rows = _execute(
        """
        SELECT
            e.event_id, e.vehicle_id, e.date, e.event_type, e.title,
            e.time, e.location, e.importance, e.prep_required,
            v.identifier, v.vehicle_type, v.our_posture, v.heat_score,
            v.owner_internal, v.lobbyist_task
        FROM bf_calendar_events e
        JOIN bf_vehicles v ON e.vehicle_id = v.vehicle_id
        WHERE e.date >= :today
          AND e.date <= :end_date
          AND e.passed = 0
          AND e.cancelled = 0
        ORDER BY e.date ASC, e.importance DESC
        """,
        {"today": today, "end_date": end_date},
    )

    events = []
    for row in rows:
        event = dict(row)
        event["days_until"] = _days_until(row["date"])
        events.append(event)

    return events
