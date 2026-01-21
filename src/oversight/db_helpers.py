"""Database helpers for Oversight Monitor tables."""

import json
from datetime import datetime, timezone
from typing import Optional

from src.db import connect


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def insert_om_event(event: dict) -> None:
    """Insert a canonical event."""
    con = connect()
    con.execute(
        """
        INSERT INTO om_events (
            event_id, event_type, theme, primary_source_type, primary_url,
            pub_timestamp, pub_precision, pub_source,
            event_timestamp, event_precision, event_source,
            title, summary, raw_content,
            is_escalation, escalation_signals, is_deviation, deviation_reason,
            canonical_refs, fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event["event_id"],
            event["event_type"],
            event.get("theme"),
            event["primary_source_type"],
            event["primary_url"],
            event.get("pub_timestamp"),
            event.get("pub_precision", "unknown"),
            event.get("pub_source", "missing"),
            event.get("event_timestamp"),
            event.get("event_precision"),
            event.get("event_source"),
            event["title"],
            event.get("summary"),
            event.get("raw_content"),
            1 if event.get("is_escalation") else 0,
            json.dumps(event.get("escalation_signals")) if event.get("escalation_signals") else None,
            1 if event.get("is_deviation") else 0,
            event.get("deviation_reason"),
            json.dumps(event.get("canonical_refs")) if event.get("canonical_refs") else None,
            event["fetched_at"],
        ),
    )
    con.commit()
    con.close()


def get_om_event(event_id: str) -> Optional[dict]:
    """Get a canonical event by ID."""
    con = connect()
    con.row_factory = None
    cur = con.execute(
        """
        SELECT event_id, event_type, theme, primary_source_type, primary_url,
               pub_timestamp, pub_precision, pub_source,
               event_timestamp, event_precision, event_source,
               title, summary, raw_content,
               is_escalation, escalation_signals, is_deviation, deviation_reason,
               canonical_refs, surfaced, surfaced_at, surfaced_via,
               fetched_at, created_at, updated_at
        FROM om_events WHERE event_id = ?
        """,
        (event_id,),
    )
    row = cur.fetchone()
    con.close()

    if not row:
        return None

    return {
        "event_id": row[0],
        "event_type": row[1],
        "theme": row[2],
        "primary_source_type": row[3],
        "primary_url": row[4],
        "pub_timestamp": row[5],
        "pub_precision": row[6],
        "pub_source": row[7],
        "event_timestamp": row[8],
        "event_precision": row[9],
        "event_source": row[10],
        "title": row[11],
        "summary": row[12],
        "raw_content": row[13],
        "is_escalation": row[14],
        "escalation_signals": json.loads(row[15]) if row[15] else None,
        "is_deviation": row[16],
        "deviation_reason": row[17],
        "canonical_refs": json.loads(row[18]) if row[18] else None,
        "surfaced": row[19],
        "surfaced_at": row[20],
        "surfaced_via": row[21],
        "fetched_at": row[22],
        "created_at": row[23],
        "updated_at": row[24],
    }


def update_om_event_surfaced(event_id: str, surfaced_via: str) -> None:
    """Mark an event as surfaced."""
    con = connect()
    con.execute(
        """
        UPDATE om_events
        SET surfaced = 1, surfaced_at = ?, surfaced_via = ?, updated_at = ?
        WHERE event_id = ?
        """,
        (_utc_now_iso(), surfaced_via, _utc_now_iso(), event_id),
    )
    con.commit()
    con.close()


def insert_om_rejected(rejected: dict) -> int:
    """Insert a rejected event. Returns the row ID."""
    con = connect()
    cur = con.execute(
        """
        INSERT INTO om_rejected (
            source_type, url, title, pub_timestamp,
            rejection_reason, routine_explanation, fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            rejected["source_type"],
            rejected["url"],
            rejected.get("title"),
            rejected.get("pub_timestamp"),
            rejected["rejection_reason"],
            rejected.get("routine_explanation"),
            rejected["fetched_at"],
        ),
    )
    row_id = cur.lastrowid
    con.commit()
    con.close()
    return row_id


def get_om_events_for_digest(
    start_date: str,
    end_date: str,
    surfaced_only: bool = False,
) -> list[dict]:
    """Get events for weekly digest (deviations and escalations)."""
    con = connect()
    con.row_factory = None

    query = """
        SELECT event_id, event_type, theme, primary_source_type, primary_url,
               pub_timestamp, pub_precision, pub_source,
               event_timestamp, event_precision, event_source,
               title, summary, is_escalation, escalation_signals,
               is_deviation, deviation_reason, canonical_refs,
               surfaced, surfaced_at
        FROM om_events
        WHERE pub_timestamp >= ? AND pub_timestamp <= ?
          AND (is_escalation = 1 OR is_deviation = 1)
    """
    params = [start_date, end_date]

    if surfaced_only:
        query += " AND surfaced = 1"

    query += " ORDER BY pub_timestamp DESC"

    cur = con.execute(query, params)
    rows = cur.fetchall()
    con.close()

    return [
        {
            "event_id": row[0],
            "event_type": row[1],
            "theme": row[2],
            "primary_source_type": row[3],
            "primary_url": row[4],
            "pub_timestamp": row[5],
            "pub_precision": row[6],
            "pub_source": row[7],
            "event_timestamp": row[8],
            "event_precision": row[9],
            "event_source": row[10],
            "title": row[11],
            "summary": row[12],
            "is_escalation": row[13],
            "escalation_signals": json.loads(row[14]) if row[14] else None,
            "is_deviation": row[15],
            "deviation_reason": row[16],
            "canonical_refs": json.loads(row[17]) if row[17] else None,
            "surfaced": row[18],
            "surfaced_at": row[19],
        }
        for row in rows
    ]


def insert_om_escalation_signal(signal: dict) -> int:
    """Insert an escalation signal. Returns the row ID."""
    con = connect()
    cur = con.execute(
        """
        INSERT INTO om_escalation_signals (
            signal_pattern, signal_type, severity, description
        ) VALUES (?, ?, ?, ?)
        """,
        (
            signal["signal_pattern"],
            signal["signal_type"],
            signal["severity"],
            signal.get("description"),
        ),
    )
    row_id = cur.lastrowid
    con.commit()
    con.close()
    return row_id


def get_active_escalation_signals() -> list[dict]:
    """Get all active escalation signals."""
    con = connect()
    con.row_factory = None
    cur = con.execute(
        """
        SELECT id, signal_pattern, signal_type, severity, description
        FROM om_escalation_signals
        WHERE active = 1
        """
    )
    rows = cur.fetchall()
    con.close()

    return [
        {
            "id": row[0],
            "signal_pattern": row[1],
            "signal_type": row[2],
            "severity": row[3],
            "description": row[4],
        }
        for row in rows
    ]
