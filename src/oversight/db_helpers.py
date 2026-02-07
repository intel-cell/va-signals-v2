"""Database helpers for Oversight Monitor tables."""

import json
from datetime import UTC, datetime

from src.db import connect, execute, insert_returning_id


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def insert_om_event(event: dict) -> None:
    """Insert a canonical event."""
    con = connect()
    execute(
        con,
        """
        INSERT INTO om_events (
            event_id, event_type, theme, primary_source_type, primary_url,
            pub_timestamp, pub_precision, pub_source,
            event_timestamp, event_precision, event_source,
            title, summary, raw_content,
            is_escalation, escalation_signals, ml_score, ml_risk_level,
            is_deviation, deviation_reason,
            canonical_refs, fetched_at
        ) VALUES (
            :event_id, :event_type, :theme, :primary_source_type, :primary_url,
            :pub_timestamp, :pub_precision, :pub_source,
            :event_timestamp, :event_precision, :event_source,
            :title, :summary, :raw_content,
            :is_escalation, :escalation_signals, :ml_score, :ml_risk_level,
            :is_deviation, :deviation_reason,
            :canonical_refs, :fetched_at
        )
        """,
        {
            "event_id": event["event_id"],
            "event_type": event["event_type"],
            "theme": event.get("theme"),
            "primary_source_type": event["primary_source_type"],
            "primary_url": event["primary_url"],
            "pub_timestamp": event.get("pub_timestamp"),
            "pub_precision": event.get("pub_precision", "unknown"),
            "pub_source": event.get("pub_source", "missing"),
            "event_timestamp": event.get("event_timestamp"),
            "event_precision": event.get("event_precision"),
            "event_source": event.get("event_source"),
            "title": event["title"],
            "summary": event.get("summary"),
            "raw_content": event.get("raw_content"),
            "is_escalation": 1 if event.get("is_escalation") else 0,
            "escalation_signals": json.dumps(event.get("escalation_signals"))
            if event.get("escalation_signals")
            else None,
            "ml_score": event.get("ml_score"),
            "ml_risk_level": event.get("ml_risk_level"),
            "is_deviation": 1 if event.get("is_deviation") else 0,
            "deviation_reason": event.get("deviation_reason"),
            "canonical_refs": json.dumps(event.get("canonical_refs"))
            if event.get("canonical_refs")
            else None,
            "fetched_at": event["fetched_at"],
        },
    )
    con.commit()
    con.close()


def get_om_event(event_id: str) -> dict | None:
    """Get a canonical event by ID."""
    con = connect()
    cur = execute(
        con,
        """
        SELECT event_id, event_type, theme, primary_source_type, primary_url,
               pub_timestamp, pub_precision, pub_source,
               event_timestamp, event_precision, event_source,
               title, summary, raw_content,
               is_escalation, escalation_signals, is_deviation, deviation_reason,
               canonical_refs, surfaced, surfaced_at, surfaced_via,
               fetched_at, created_at, updated_at
        FROM om_events WHERE event_id = :event_id
        """,
        {"event_id": event_id},
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
    execute(
        con,
        """
        UPDATE om_events
        SET surfaced = 1, surfaced_at = :surfaced_at, surfaced_via = :surfaced_via, updated_at = :updated_at
        WHERE event_id = :event_id
        """,
        {
            "surfaced_at": _utc_now_iso(),
            "surfaced_via": surfaced_via,
            "updated_at": _utc_now_iso(),
            "event_id": event_id,
        },
    )
    con.commit()
    con.close()


def insert_om_rejected(rejected: dict) -> int:
    """Insert a rejected event. Returns the row ID."""
    con = connect()
    row_id = insert_returning_id(
        con,
        """
        INSERT INTO om_rejected (
            source_type, url, title, pub_timestamp,
            rejection_reason, routine_explanation, fetched_at
        ) VALUES (
            :source_type, :url, :title, :pub_timestamp,
            :rejection_reason, :routine_explanation, :fetched_at
        )
        """,
        {
            "source_type": rejected["source_type"],
            "url": rejected["url"],
            "title": rejected.get("title"),
            "pub_timestamp": rejected.get("pub_timestamp"),
            "rejection_reason": rejected["rejection_reason"],
            "routine_explanation": rejected.get("routine_explanation"),
            "fetched_at": rejected["fetched_at"],
        },
    )
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

    query = """
        SELECT event_id, event_type, theme, primary_source_type, primary_url,
               pub_timestamp, pub_precision, pub_source,
               event_timestamp, event_precision, event_source,
               title, summary, is_escalation, escalation_signals,
               is_deviation, deviation_reason, canonical_refs,
               surfaced, surfaced_at
        FROM om_events
        WHERE pub_timestamp >= :start_date AND pub_timestamp <= :end_date
          AND (is_escalation = 1 OR is_deviation = 1)
    """
    params = {"start_date": start_date, "end_date": end_date}

    if surfaced_only:
        query += " AND surfaced = 1"

    query += " ORDER BY pub_timestamp DESC"

    cur = execute(con, query, params)
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
    row_id = insert_returning_id(
        con,
        """
        INSERT INTO om_escalation_signals (
            signal_pattern, signal_type, severity, description
        ) VALUES (:signal_pattern, :signal_type, :severity, :description)
        """,
        {
            "signal_pattern": signal["signal_pattern"],
            "signal_type": signal["signal_type"],
            "severity": signal["severity"],
            "description": signal.get("description"),
        },
    )
    con.commit()
    con.close()
    return row_id


def get_active_escalation_signals() -> list[dict]:
    """Get all active escalation signals."""
    con = connect()
    cur = execute(
        con,
        """
        SELECT id, signal_pattern, signal_type, severity, description
        FROM om_escalation_signals
        WHERE active = 1
        """,
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


DEFAULT_ESCALATION_SIGNALS = [
    {
        "signal_pattern": "criminal referral",
        "signal_type": "phrase",
        "severity": "critical",
        "description": "GAO/OIG referred matter for prosecution",
    },
    {
        "signal_pattern": "subpoena",
        "signal_type": "keyword",
        "severity": "critical",
        "description": "Congressional subpoena issued",
    },
    {
        "signal_pattern": "emergency hearing",
        "signal_type": "phrase",
        "severity": "critical",
        "description": "Unscheduled urgent hearing",
    },
    {
        "signal_pattern": "whistleblower",
        "signal_type": "keyword",
        "severity": "high",
        "description": "Whistleblower testimony or complaint",
    },
    {
        "signal_pattern": "investigation launched",
        "signal_type": "phrase",
        "severity": "high",
        "description": "New formal investigation opened",
    },
    {
        "signal_pattern": "fraud",
        "signal_type": "keyword",
        "severity": "high",
        "description": "Fraud allegation or finding",
    },
    {
        "signal_pattern": "arrest",
        "signal_type": "keyword",
        "severity": "critical",
        "description": "Criminal arrest related to VA",
    },
    {
        "signal_pattern": "first-ever",
        "signal_type": "phrase",
        "severity": "medium",
        "description": "Unprecedented action",
    },
    {
        "signal_pattern": "reversal",
        "signal_type": "keyword",
        "severity": "medium",
        "description": "Policy or legal reversal",
    },
    {
        "signal_pattern": "bipartisan letter",
        "signal_type": "phrase",
        "severity": "medium",
        "description": "Cross-party congressional action",
    },
    {
        "signal_pattern": "precedential opinion",
        "signal_type": "phrase",
        "severity": "high",
        "description": "CAFC precedential ruling",
    },
]


def seed_default_escalation_signals() -> int:
    """Seed default escalation signals if not already present. Returns count inserted."""
    existing = get_active_escalation_signals()
    existing_patterns = {s["signal_pattern"] for s in existing}

    inserted = 0
    for signal in DEFAULT_ESCALATION_SIGNALS:
        if signal["signal_pattern"] not in existing_patterns:
            insert_om_escalation_signal(signal)
            inserted += 1

    return inserted


def update_canonical_refs(event_id: str, refs: dict) -> None:
    """Merge new canonical refs into an existing event's canonical_refs JSON."""
    con = connect()
    cur = execute(
        con,
        "SELECT canonical_refs FROM om_events WHERE event_id = :event_id",
        {"event_id": event_id},
    )
    row = cur.fetchone()
    if not row:
        con.close()
        return

    existing = json.loads(row[0]) if row[0] else {}
    existing.update(refs)

    execute(
        con,
        """UPDATE om_events
           SET canonical_refs = :canonical_refs, updated_at = :updated_at
           WHERE event_id = :event_id""",
        {
            "canonical_refs": json.dumps(existing),
            "updated_at": _utc_now_iso(),
            "event_id": event_id,
        },
    )
    con.commit()
    con.close()


def get_oversight_stats() -> dict:
    """Return aggregate statistics for oversight events."""
    con = connect()

    cur = execute(con, "SELECT COUNT(*) FROM om_events")
    total_events = cur.fetchone()[0]

    cur = execute(con, "SELECT COUNT(*) FROM om_events WHERE is_escalation = 1")
    escalations = cur.fetchone()[0]

    cur = execute(con, "SELECT COUNT(*) FROM om_events WHERE is_deviation = 1")
    deviations = cur.fetchone()[0]

    cur = execute(con, "SELECT COUNT(*) FROM om_events WHERE surfaced = 1")
    surfaced = cur.fetchone()[0]

    cur = execute(con, "SELECT MAX(fetched_at) FROM om_events")
    last_event_at = cur.fetchone()[0]

    cur = execute(
        con,
        """
        SELECT primary_source_type, COUNT(*)
        FROM om_events
        GROUP BY primary_source_type
        ORDER BY COUNT(*) DESC
        """,
    )
    by_source = {row[0]: row[1] for row in cur.fetchall()}

    con.close()
    return {
        "total_events": total_events,
        "escalations": escalations,
        "deviations": deviations,
        "surfaced": surfaced,
        "last_event_at": last_event_at,
        "by_source": by_source,
    }


def get_oversight_events(
    limit: int = 50,
    source_type: str | None = None,
    escalations_only: bool = False,
    deviations_only: bool = False,
    surfaced_only: bool = False,
) -> list[dict]:
    """Return recent oversight events with optional filters."""
    con = connect()

    query = """
        SELECT event_id, title, primary_source_type, primary_url,
               pub_timestamp, is_escalation, is_deviation, surfaced,
               surfaced_at, fetched_at
        FROM om_events
        WHERE 1=1
    """
    params: dict[str, object] = {}

    if source_type:
        query += " AND primary_source_type = :source_type"
        params["source_type"] = source_type
    if escalations_only:
        query += " AND is_escalation = 1"
    if deviations_only:
        query += " AND is_deviation = 1"
    if surfaced_only:
        query += " AND surfaced = 1"

    query += " ORDER BY COALESCE(pub_timestamp, fetched_at) DESC LIMIT :limit"
    params["limit"] = limit

    cur = execute(con, query, params)
    rows = cur.fetchall()
    con.close()

    return [
        {
            "event_id": row[0],
            "title": row[1],
            "primary_source_type": row[2],
            "primary_url": row[3],
            "pub_timestamp": row[4],
            "is_escalation": bool(row[5]),
            "is_deviation": bool(row[6]),
            "surfaced": bool(row[7]),
            "surfaced_at": row[8],
            "fetched_at": row[9],
        }
        for row in rows
    ]
