"""Hearings database functions."""

import logging
from datetime import datetime
from typing import Any

from .core import connect, execute, insert_returning_id
from .helpers import _utc_now_iso

logger = logging.getLogger(__name__)


def _hearing_row_to_dict(row) -> dict:
    """Convert a hearing row to a dictionary."""
    return {
        "event_id": row[0],
        "congress": row[1],
        "chamber": row[2],
        "committee_code": row[3],
        "committee_name": row[4],
        "hearing_date": row[5],
        "hearing_time": row[6],
        "title": row[7],
        "meeting_type": row[8],
        "status": row[9],
        "location": row[10],
        "url": row[11],
        "witnesses_json": row[12],
        "first_seen_at": row[13],
        "updated_at": row[14],
    }


def upsert_hearing(hearing: dict) -> tuple[bool, list[dict]]:
    """
    Insert or update a hearing. Returns (is_new, changes_list).
    is_new is True if this is a new hearing.
    changes_list contains dicts with field_changed, old_value, new_value for any changed fields.

    Expected keys: event_id, congress, chamber, committee_code, committee_name,
    hearing_date, hearing_time, title, meeting_type, status, location, url, witnesses_json.
    """
    # Reject placeholder/far-future dates
    hearing_date = hearing.get("hearing_date", "")
    if hearing_date:
        try:
            dt = datetime.fromisoformat(hearing_date[:10])
            if dt.year >= 2099:
                logger.warning(
                    "Rejecting hearing with far-future date: event_id=%s date=%s",
                    hearing.get("event_id"),
                    hearing_date,
                )
                return (False, [])
        except (ValueError, TypeError):
            pass  # let downstream handle unparseable dates

    con = connect()
    now = _utc_now_iso()

    # Check if exists and get current values
    cur = execute(
        con,
        """SELECT event_id, congress, chamber, committee_code, committee_name,
           hearing_date, hearing_time, title, meeting_type, status, location, url,
           witnesses_json, first_seen_at, updated_at
           FROM hearings WHERE event_id = :event_id""",
        {"event_id": hearing["event_id"]},
    )
    existing = cur.fetchone()

    if existing is None:
        # New hearing - insert
        execute(
            con,
            """INSERT INTO hearings(event_id, congress, chamber, committee_code, committee_name,
               hearing_date, hearing_time, title, meeting_type, status, location, url,
               witnesses_json, first_seen_at, updated_at)
               VALUES(:event_id, :congress, :chamber, :committee_code, :committee_name,
                      :hearing_date, :hearing_time, :title, :meeting_type, :status, :location, :url,
                      :witnesses_json, :first_seen_at, :updated_at)""",
            {
                "event_id": hearing["event_id"],
                "congress": hearing["congress"],
                "chamber": hearing["chamber"],
                "committee_code": hearing["committee_code"],
                "committee_name": hearing.get("committee_name"),
                "hearing_date": hearing["hearing_date"],
                "hearing_time": hearing.get("hearing_time"),
                "title": hearing.get("title"),
                "meeting_type": hearing.get("meeting_type"),
                "status": hearing["status"],
                "location": hearing.get("location"),
                "url": hearing.get("url"),
                "witnesses_json": hearing.get("witnesses_json"),
                "first_seen_at": now,
                "updated_at": now,
            },
        )
        con.commit()
        con.close()
        return (True, [])

    # Existing hearing - check for changes
    existing_dict = _hearing_row_to_dict(existing)
    changes = []

    # Fields to track for changes
    tracked_fields = [
        "status",
        "hearing_date",
        "hearing_time",
        "title",
        "location",
        "witnesses_json",
    ]

    for field in tracked_fields:
        old_val = existing_dict.get(field)
        new_val = hearing.get(field)
        # Normalize None vs empty string comparison
        if (
            old_val != new_val
            and not (old_val is None and new_val == "")
            and not (old_val == "" and new_val is None)
        ):
            changes.append(
                {
                    "field_changed": field,
                    "old_value": old_val,
                    "new_value": new_val,
                }
            )

    # Update the record if there are changes
    if changes:
        execute(
            con,
            """UPDATE hearings
               SET congress=:congress, chamber=:chamber, committee_code=:committee_code, committee_name=:committee_name,
                   hearing_date=:hearing_date, hearing_time=:hearing_time, title=:title, meeting_type=:meeting_type,
                   status=:status, location=:location, url=:url, witnesses_json=:witnesses_json, updated_at=:updated_at
               WHERE event_id=:event_id""",
            {
                "event_id": hearing["event_id"],
                "congress": hearing["congress"],
                "chamber": hearing["chamber"],
                "committee_code": hearing["committee_code"],
                "committee_name": hearing.get("committee_name"),
                "hearing_date": hearing["hearing_date"],
                "hearing_time": hearing.get("hearing_time"),
                "title": hearing.get("title"),
                "meeting_type": hearing.get("meeting_type"),
                "status": hearing["status"],
                "location": hearing.get("location"),
                "url": hearing.get("url"),
                "witnesses_json": hearing.get("witnesses_json"),
                "updated_at": now,
            },
        )

        # Record each change in hearing_updates
        for change in changes:
            execute(
                con,
                """INSERT INTO hearing_updates(event_id, field_changed, old_value, new_value, detected_at)
                   VALUES(:event_id, :field_changed, :old_value, :new_value, :detected_at)""",
                {
                    "event_id": hearing["event_id"],
                    "field_changed": change["field_changed"],
                    "old_value": change["old_value"],
                    "new_value": change["new_value"],
                    "detected_at": now,
                },
            )
        con.commit()

    con.close()
    return (False, changes)


def get_hearing(event_id: str) -> dict | None:
    """Get a single hearing by event_id."""
    con = connect()
    cur = execute(
        con,
        """SELECT event_id, congress, chamber, committee_code, committee_name,
           hearing_date, hearing_time, title, meeting_type, status, location, url,
           witnesses_json, first_seen_at, updated_at
           FROM hearings WHERE event_id = :event_id""",
        {"event_id": event_id},
    )
    row = cur.fetchone()
    con.close()
    if not row:
        return None
    return _hearing_row_to_dict(row)


def get_hearings(upcoming: bool = True, limit: int = 20, committee: str = None) -> list[dict]:
    """
    Get hearings, optionally filtered.
    If upcoming=True, returns hearings with hearing_date >= today.
    If committee is provided, filters by committee_code.
    """
    con = connect()

    from datetime import date

    today = date.today().isoformat()

    query = """SELECT event_id, congress, chamber, committee_code, committee_name,
               hearing_date, hearing_time, title, meeting_type, status, location, url,
               witnesses_json, first_seen_at, updated_at
               FROM hearings WHERE 1=1"""
    params: dict[str, Any] = {}

    if upcoming:
        query += " AND hearing_date >= :today"
        params["today"] = today

    if committee:
        query += " AND committee_code = :committee_code"
        params["committee_code"] = committee

    query += " ORDER BY hearing_date ASC, hearing_time ASC LIMIT :limit"
    params["limit"] = limit

    cur = execute(con, query, params)
    rows = cur.fetchall()
    con.close()
    return [_hearing_row_to_dict(r) for r in rows]


def insert_hearing_update(event_id: str, field: str, old_val: str, new_val: str) -> int:
    """Insert a hearing update record manually. Returns the new record ID."""
    con = connect()
    now = _utc_now_iso()
    update_id = insert_returning_id(
        con,
        """INSERT INTO hearing_updates(event_id, field_changed, old_value, new_value, detected_at)
           VALUES(:event_id, :field_changed, :old_value, :new_value, :detected_at)""",
        {
            "event_id": event_id,
            "field_changed": field,
            "old_value": old_val,
            "new_value": new_val,
            "detected_at": now,
        },
    )
    con.commit()
    con.close()
    return update_id


def get_hearing_updates(event_id: str = None, limit: int = 50) -> list[dict]:
    """
    Get hearing updates, optionally filtered by event_id.
    Returns updates ordered by detected_at descending.
    """
    con = connect()

    if event_id:
        cur = execute(
            con,
            """SELECT u.id, u.event_id, u.field_changed, u.old_value, u.new_value, u.detected_at,
                      h.title, h.committee_name
               FROM hearing_updates u
               JOIN hearings h ON u.event_id = h.event_id
               WHERE u.event_id = :event_id
               ORDER BY u.detected_at DESC LIMIT :limit""",
            {"event_id": event_id, "limit": limit},
        )
    else:
        cur = execute(
            con,
            """SELECT u.id, u.event_id, u.field_changed, u.old_value, u.new_value, u.detected_at,
                      h.title, h.committee_name
               FROM hearing_updates u
               JOIN hearings h ON u.event_id = h.event_id
               ORDER BY u.detected_at DESC LIMIT :limit""",
            {"limit": limit},
        )

    rows = cur.fetchall()
    con.close()
    return [
        {
            "id": r[0],
            "event_id": r[1],
            "field_changed": r[2],
            "old_value": r[3],
            "new_value": r[4],
            "detected_at": r[5],
            "hearing_title": r[6],
            "committee_name": r[7],
        }
        for r in rows
    ]


def get_new_hearings_since(since: str) -> list[dict]:
    """Get hearings first seen after the given ISO timestamp."""
    con = connect()
    cur = execute(
        con,
        """SELECT event_id, congress, chamber, committee_code, committee_name,
           hearing_date, hearing_time, title, meeting_type, status, location, url,
           witnesses_json, first_seen_at, updated_at
           FROM hearings WHERE first_seen_at > :since
           ORDER BY first_seen_at DESC""",
        {"since": since},
    )
    rows = cur.fetchall()
    con.close()
    return [_hearing_row_to_dict(r) for r in rows]


def get_hearing_changes_since(since: str) -> list[dict]:
    """Get hearing updates detected after the given ISO timestamp."""
    con = connect()
    cur = execute(
        con,
        """SELECT u.id, u.event_id, u.field_changed, u.old_value, u.new_value, u.detected_at,
                  h.title, h.committee_name, h.hearing_date
           FROM hearing_updates u
           JOIN hearings h ON u.event_id = h.event_id
           WHERE u.detected_at > :since
           ORDER BY u.detected_at DESC""",
        {"since": since},
    )
    rows = cur.fetchall()
    con.close()
    return [
        {
            "id": r[0],
            "event_id": r[1],
            "field_changed": r[2],
            "old_value": r[3],
            "new_value": r[4],
            "detected_at": r[5],
            "hearing_title": r[6],
            "committee_name": r[7],
            "hearing_date": r[8],
        }
        for r in rows
    ]


def get_hearing_stats() -> dict:
    """
    Get summary statistics for hearings tracking.
    Returns {total, upcoming, by_committee, by_status}.
    """
    con = connect()

    from datetime import date

    today = date.today().isoformat()

    # Total hearings
    cur = execute(con, "SELECT COUNT(*) FROM hearings")
    total = cur.fetchone()[0]

    # Upcoming hearings (hearing_date >= today)
    cur = execute(
        con,
        "SELECT COUNT(*) FROM hearings WHERE hearing_date >= :today",
        {"today": today},
    )
    upcoming = cur.fetchone()[0]

    # By committee
    cur = execute(
        con,
        """SELECT committee_code, committee_name, COUNT(*)
           FROM hearings GROUP BY committee_code
           ORDER BY COUNT(*) DESC""",
    )
    by_committee = {r[0]: {"name": r[1], "count": r[2]} for r in cur.fetchall()}

    # By status
    cur = execute(con, "SELECT status, COUNT(*) FROM hearings GROUP BY status")
    by_status = {r[0]: r[1] for r in cur.fetchall()}

    con.close()
    return {
        "total": total,
        "upcoming": upcoming,
        "by_committee": by_committee,
        "by_status": by_status,
    }
