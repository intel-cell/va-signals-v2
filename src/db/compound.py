"""Compound signals database functions."""

import json
from typing import Optional

from .core import connect, execute
from .helpers import _utc_now_iso


def insert_compound_signal(data: dict) -> Optional[str]:
    """
    Insert a compound signal. Skips if compound_id already exists.

    Returns:
        compound_id if inserted, None if already existed.
    """
    con = connect()
    try:
        cur = execute(
            con,
            "SELECT compound_id FROM compound_signals WHERE compound_id = :compound_id",
            {"compound_id": data["compound_id"]},
        )
        if cur.fetchone():
            return None

        execute(
            con,
            """INSERT INTO compound_signals (
                compound_id, rule_id, severity_score, narrative,
                temporal_window_hours, member_events, topics, created_at
            ) VALUES (
                :compound_id, :rule_id, :severity_score, :narrative,
                :temporal_window_hours, :member_events, :topics, :created_at
            )""",
            data,
        )
        con.commit()
        return data["compound_id"]
    finally:
        con.close()


def get_compound_signal(compound_id: str) -> Optional[dict]:
    """Get a single compound signal by ID."""
    con = connect()
    cur = execute(
        con,
        """SELECT compound_id, rule_id, severity_score, narrative,
                  temporal_window_hours, member_events, topics, created_at, resolved_at
           FROM compound_signals
           WHERE compound_id = :compound_id""",
        {"compound_id": compound_id},
    )
    row = cur.fetchone()
    con.close()
    if row is None:
        return None
    return _row_to_dict(row)


def get_compound_signals(
    limit: int = 50,
    offset: int = 0,
    rule_id: Optional[str] = None,
    min_severity: Optional[float] = None,
) -> list[dict]:
    """Get compound signals with optional filtering."""
    con = connect()
    clauses = []
    params: dict = {"limit": limit, "offset": offset}

    if rule_id:
        clauses.append("rule_id = :rule_id")
        params["rule_id"] = rule_id

    if min_severity is not None:
        clauses.append("severity_score >= :min_severity")
        params["min_severity"] = min_severity

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    cur = execute(
        con,
        f"""SELECT compound_id, rule_id, severity_score, narrative,
                   temporal_window_hours, member_events, topics, created_at, resolved_at
            FROM compound_signals
            {where}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset""",
        params,
    )
    rows = cur.fetchall()
    con.close()
    return [_row_to_dict(r) for r in rows]


def resolve_compound_signal(compound_id: str) -> bool:
    """Mark a compound signal as resolved. Returns True if updated."""
    con = connect()
    now = _utc_now_iso()
    cur = execute(
        con,
        """UPDATE compound_signals
           SET resolved_at = :resolved_at
           WHERE compound_id = :compound_id AND resolved_at IS NULL""",
        {"compound_id": compound_id, "resolved_at": now},
    )
    con.commit()
    updated = cur.rowcount > 0
    con.close()
    return updated


def get_compound_stats() -> dict:
    """Get aggregate statistics for compound signals."""
    con = connect()

    cur = execute(con, "SELECT COUNT(*) FROM compound_signals")
    total = cur.fetchone()[0]

    cur = execute(con, "SELECT COUNT(*) FROM compound_signals WHERE resolved_at IS NULL")
    unresolved = cur.fetchone()[0]

    cur = execute(
        con,
        "SELECT rule_id, COUNT(*) FROM compound_signals GROUP BY rule_id",
    )
    by_rule = dict(cur.fetchall())

    con.close()
    return {
        "total": total,
        "unresolved": unresolved,
        "resolved": total - unresolved,
        "by_rule": by_rule,
    }


def _row_to_dict(row) -> dict:
    return {
        "compound_id": row[0],
        "rule_id": row[1],
        "severity_score": row[2],
        "narrative": row[3],
        "temporal_window_hours": row[4],
        "member_events": json.loads(row[5]) if row[5] else [],
        "topics": json.loads(row[6]) if row[6] else [],
        "created_at": row[7],
        "resolved_at": row[8],
    }
