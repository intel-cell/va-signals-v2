"""
Database helpers for CEO Brief pipeline.

Handles storage and retrieval of generated briefs, plus queries
to fetch deltas from all source tables.
"""

import json
from datetime import date, datetime, timedelta
from typing import Optional

from ..db import connect, execute


# ============================================================================
# CEO BRIEF STORAGE
# ============================================================================


def ensure_ceo_briefs_table(con=None) -> None:
    """Create CEO briefs table if it doesn't exist."""
    from ..db import init_db
    init_db()


def insert_ceo_brief(
    brief_id: str,
    generated_at: datetime,
    period_start: date,
    period_end: date,
    objective: str,
    content_json: str,
    markdown_output: str,
    validation_errors: Optional[list[str]] = None,
    status: str = "draft",
) -> bool:
    """
    Insert a new CEO brief into the database.

    Returns True if inserted, False if brief_id already exists.
    """
    con = connect()
    ensure_ceo_briefs_table(con)

    # Check if exists
    cur = execute(
        con, "SELECT brief_id FROM ceo_briefs WHERE brief_id = :brief_id", {"brief_id": brief_id}
    )
    if cur.fetchone():
        con.close()
        return False

    execute(
        con,
        """
        INSERT INTO ceo_briefs (
            brief_id, generated_at, period_start, period_end,
            objective, content_json, markdown_output, validation_errors, status
        ) VALUES (
            :brief_id, :generated_at, :period_start, :period_end,
            :objective, :content_json, :markdown_output, :validation_errors, :status
        )
        """,
        {
            "brief_id": brief_id,
            "generated_at": generated_at.isoformat(),
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "objective": objective,
            "content_json": content_json,
            "markdown_output": markdown_output,
            "validation_errors": json.dumps(validation_errors) if validation_errors else None,
            "status": status,
        },
    )
    con.commit()
    con.close()
    return True


def update_brief_status(brief_id: str, status: str) -> bool:
    """Update the status of a brief (draft, validated, published)."""
    con = connect()
    execute(
        con,
        """
        UPDATE ceo_briefs
        SET status = :status, updated_at = datetime('now')
        WHERE brief_id = :brief_id
        """,
        {"brief_id": brief_id, "status": status},
    )
    affected = con.total_changes
    con.commit()
    con.close()
    return affected > 0


def get_ceo_brief(brief_id: str) -> Optional[dict]:
    """Retrieve a CEO brief by ID."""
    con = connect()
    ensure_ceo_briefs_table(con)

    cur = execute(con, "SELECT * FROM ceo_briefs WHERE brief_id = :brief_id", {"brief_id": brief_id})
    row = cur.fetchone()
    con.close()

    if not row:
        return None

    return {
        "brief_id": row[0],
        "generated_at": row[1],
        "period_start": row[2],
        "period_end": row[3],
        "objective": row[4],
        "content_json": row[5],
        "markdown_output": row[6],
        "validation_errors": json.loads(row[7]) if row[7] else None,
        "status": row[8],
        "created_at": row[9],
        "updated_at": row[10],
    }


def get_latest_brief() -> Optional[dict]:
    """Get the most recently generated CEO brief."""
    con = connect()
    ensure_ceo_briefs_table(con)

    cur = execute(
        con,
        "SELECT * FROM ceo_briefs ORDER BY generated_at DESC LIMIT 1",
    )
    row = cur.fetchone()
    con.close()

    if not row:
        return None

    return {
        "brief_id": row[0],
        "generated_at": row[1],
        "period_start": row[2],
        "period_end": row[3],
        "objective": row[4],
        "content_json": row[5],
        "markdown_output": row[6],
        "validation_errors": json.loads(row[7]) if row[7] else None,
        "status": row[8],
        "created_at": row[9],
        "updated_at": row[10],
    }


def list_briefs(limit: int = 10) -> list[dict]:
    """List recent CEO briefs (metadata only)."""
    con = connect()
    ensure_ceo_briefs_table(con)

    cur = execute(
        con,
        """
        SELECT brief_id, generated_at, period_start, period_end, objective, status, created_at
        FROM ceo_briefs
        ORDER BY generated_at DESC
        LIMIT :limit
        """,
        {"limit": limit},
    )
    rows = cur.fetchall()
    con.close()

    return [
        {
            "brief_id": r[0],
            "generated_at": r[1],
            "period_start": r[2],
            "period_end": r[3],
            "objective": r[4],
            "status": r[5],
            "created_at": r[6],
        }
        for r in rows
    ]


# ============================================================================
# DELTA QUERIES - Fetch changes from all source tables
# ============================================================================


def get_fr_deltas(since: datetime, until: datetime) -> list[dict]:
    """
    Get Federal Register documents first seen in the period.

    Joins with fr_summaries if available for enriched content.
    """
    con = connect()
    cur = execute(
        con,
        """
        SELECT
            f.doc_id,
            f.published_date,
            f.first_seen_at,
            f.source_url,
            s.summary,
            s.bullet_points,
            s.veteran_impact,
            s.tags
        FROM fr_seen f
        LEFT JOIN fr_summaries s ON f.doc_id = s.doc_id
        WHERE f.first_seen_at >= :since AND f.first_seen_at < :until
        ORDER BY f.first_seen_at DESC
        """,
        {"since": since.isoformat(), "until": until.isoformat()},
    )
    rows = cur.fetchall()
    con.close()

    return [
        {
            "source_type": "federal_register",
            "source_id": r[0],
            "published_date": r[1],
            "first_seen_at": r[2],
            "url": r[3],
            "summary": r[4],
            "bullet_points": r[5],
            "veteran_impact": r[6],
            "tags": r[7],
        }
        for r in rows
    ]


def get_bill_deltas(since: datetime, until: datetime) -> list[dict]:
    """
    Get bills with new actions or first seen in the period.

    Includes both new bills and existing bills with recent actions.
    """
    con = connect()

    # New bills first seen in period
    cur = execute(
        con,
        """
        SELECT
            bill_id, congress, bill_type, bill_number, title,
            sponsor_name, sponsor_party, sponsor_state,
            introduced_date, latest_action_date, latest_action_text,
            policy_area, committees_json, cosponsors_count,
            first_seen_at, updated_at
        FROM bills
        WHERE first_seen_at >= :since AND first_seen_at < :until
        ORDER BY first_seen_at DESC
        """,
        {"since": since.isoformat(), "until": until.isoformat()},
    )
    new_bills = cur.fetchall()

    # Bills with recent actions (may overlap with new bills)
    cur = execute(
        con,
        """
        SELECT DISTINCT
            b.bill_id, b.congress, b.bill_type, b.bill_number, b.title,
            b.sponsor_name, b.sponsor_party, b.sponsor_state,
            b.introduced_date, b.latest_action_date, b.latest_action_text,
            b.policy_area, b.committees_json, b.cosponsors_count,
            b.first_seen_at, b.updated_at
        FROM bills b
        JOIN bill_actions a ON b.bill_id = a.bill_id
        WHERE a.first_seen_at >= :since AND a.first_seen_at < :until
        ORDER BY b.latest_action_date DESC
        """,
        {"since": since.isoformat(), "until": until.isoformat()},
    )
    action_bills = cur.fetchall()

    # Get recent actions for bills
    bill_ids = list(set([r[0] for r in new_bills] + [r[0] for r in action_bills]))
    actions_by_bill = {}

    for bill_id in bill_ids:
        cur = execute(
            con,
            """
            SELECT action_date, action_text, action_type, first_seen_at
            FROM bill_actions
            WHERE bill_id = :bill_id AND first_seen_at >= :since
            ORDER BY action_date DESC
            LIMIT 5
            """,
            {"bill_id": bill_id, "since": since.isoformat()},
        )
        actions_by_bill[bill_id] = [
            {"date": a[0], "text": a[1], "type": a[2], "first_seen_at": a[3]}
            for a in cur.fetchall()
        ]

    con.close()

    # Combine and deduplicate
    seen_ids = set()
    results = []

    for r in new_bills + action_bills:
        if r[0] in seen_ids:
            continue
        seen_ids.add(r[0])

        results.append(
            {
                "source_type": "bill",
                "source_id": r[0],
                "congress": r[1],
                "bill_type": r[2],
                "bill_number": r[3],
                "title": r[4],
                "sponsor_name": r[5],
                "sponsor_party": r[6],
                "sponsor_state": r[7],
                "introduced_date": r[8],
                "latest_action_date": r[9],
                "latest_action_text": r[10],
                "policy_area": r[11],
                "committees_json": r[12],
                "cosponsors_count": r[13],
                "first_seen_at": r[14],
                "updated_at": r[15],
                "url": f"https://www.congress.gov/bill/{r[1]}th-congress/{r[2].lower()}/{r[3]}",
                "recent_actions": actions_by_bill.get(r[0], []),
            }
        )

    return results


def get_hearing_deltas(since: datetime, until: datetime) -> list[dict]:
    """
    Get hearings first seen or updated in the period.

    Includes hearing updates (status changes, reschedules, etc.).
    """
    con = connect()

    # New hearings
    cur = execute(
        con,
        """
        SELECT
            event_id, congress, chamber, committee_code, committee_name,
            hearing_date, hearing_time, title, meeting_type, status,
            location, url, witnesses_json, first_seen_at, updated_at
        FROM hearings
        WHERE first_seen_at >= :since AND first_seen_at < :until
        ORDER BY hearing_date DESC
        """,
        {"since": since.isoformat(), "until": until.isoformat()},
    )
    new_hearings = cur.fetchall()

    # Hearings with recent updates
    cur = execute(
        con,
        """
        SELECT DISTINCT
            h.event_id, h.congress, h.chamber, h.committee_code, h.committee_name,
            h.hearing_date, h.hearing_time, h.title, h.meeting_type, h.status,
            h.location, h.url, h.witnesses_json, h.first_seen_at, h.updated_at
        FROM hearings h
        JOIN hearing_updates u ON h.event_id = u.event_id
        WHERE u.detected_at >= :since AND u.detected_at < :until
        ORDER BY h.hearing_date DESC
        """,
        {"since": since.isoformat(), "until": until.isoformat()},
    )
    updated_hearings = cur.fetchall()

    # Get updates for all relevant hearings
    event_ids = list(set([r[0] for r in new_hearings] + [r[0] for r in updated_hearings]))
    updates_by_hearing = {}

    for event_id in event_ids:
        cur = execute(
            con,
            """
            SELECT field_changed, old_value, new_value, detected_at
            FROM hearing_updates
            WHERE event_id = :event_id AND detected_at >= :since
            ORDER BY detected_at DESC
            """,
            {"event_id": event_id, "since": since.isoformat()},
        )
        updates_by_hearing[event_id] = [
            {"field": u[0], "old": u[1], "new": u[2], "detected_at": u[3]} for u in cur.fetchall()
        ]

    con.close()

    # Combine and deduplicate
    seen_ids = set()
    results = []

    for r in new_hearings + updated_hearings:
        if r[0] in seen_ids:
            continue
        seen_ids.add(r[0])

        witnesses = []
        if r[12]:
            try:
                witnesses = json.loads(r[12])
            except json.JSONDecodeError:
                pass

        results.append(
            {
                "source_type": "hearing",
                "source_id": r[0],
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
                "url": r[11] or f"https://www.congress.gov/event/{r[1]}th-congress/{r[0]}",
                "witnesses": witnesses,
                "first_seen_at": r[13],
                "updated_at": r[14],
                "recent_updates": updates_by_hearing.get(r[0], []),
            }
        )

    return results


def get_oversight_deltas(since: datetime, until: datetime) -> list[dict]:
    """
    Get oversight monitor events created in the period.

    Prioritizes escalations and events with high significance.
    """
    con = connect()
    cur = execute(
        con,
        """
        SELECT
            event_id, event_type, theme, primary_source_type, primary_url,
            pub_timestamp, pub_precision, title, summary,
            is_escalation, escalation_signals,
            is_deviation, deviation_reason,
            canonical_refs, created_at
        FROM om_events
        WHERE created_at >= :since AND created_at < :until
        ORDER BY is_escalation DESC, pub_timestamp DESC
        """,
        {"since": since.isoformat(), "until": until.isoformat()},
    )
    rows = cur.fetchall()
    con.close()

    return [
        {
            "source_type": "oversight",
            "source_id": r[0],
            "event_type": r[1],
            "theme": r[2],
            "primary_source_type": r[3],
            "url": r[4],
            "published_date": r[5],
            "pub_precision": r[6],
            "title": r[7],
            "summary": r[8],
            "is_escalation": bool(r[9]),
            "escalation_signals": json.loads(r[10]) if r[10] else [],
            "is_deviation": bool(r[11]),
            "deviation_reason": r[12],
            "canonical_refs": json.loads(r[13]) if r[13] else {},
            "first_seen_at": r[14],
        }
        for r in rows
    ]


def get_state_deltas(since: datetime, until: datetime) -> list[dict]:
    """
    Get state intelligence signals from the period.

    Joins with classifications for severity information.
    """
    con = connect()
    cur = execute(
        con,
        """
        SELECT
            s.signal_id, s.state, s.source_id, s.program,
            s.title, s.content, s.url, s.pub_date, s.event_date,
            s.fetched_at,
            c.severity, c.classification_method, c.keywords_matched, c.llm_reasoning
        FROM state_signals s
        LEFT JOIN state_classifications c ON s.signal_id = c.signal_id
        WHERE s.fetched_at >= :since AND s.fetched_at < :until
        ORDER BY c.severity DESC, s.fetched_at DESC
        """,
        {"since": since.isoformat(), "until": until.isoformat()},
    )
    rows = cur.fetchall()
    con.close()

    return [
        {
            "source_type": "state",
            "source_id": r[0],
            "state": r[1],
            "source_name": r[2],
            "program": r[3],
            "title": r[4],
            "content": r[5],
            "url": r[6],
            "published_date": r[7],
            "event_date": r[8],
            "first_seen_at": r[9],
            "severity": r[10],
            "classification_method": r[11],
            "keywords_matched": r[12],
            "llm_reasoning": r[13],
        }
        for r in rows
    ]


def get_all_deltas(since: datetime, until: datetime) -> dict:
    """
    Get all deltas from all sources for the period.

    Returns dict with separate lists by source type plus combined total.
    """
    fr = get_fr_deltas(since, until)
    bills = get_bill_deltas(since, until)
    hearings = get_hearing_deltas(since, until)
    oversight = get_oversight_deltas(since, until)
    state = get_state_deltas(since, until)

    return {
        "period_start": since.isoformat(),
        "period_end": until.isoformat(),
        "federal_register": fr,
        "bills": bills,
        "hearings": hearings,
        "oversight": oversight,
        "state": state,
        "totals": {
            "federal_register": len(fr),
            "bills": len(bills),
            "hearings": len(hearings),
            "oversight": len(oversight),
            "state": len(state),
            "total": len(fr) + len(bills) + len(hearings) + len(oversight) + len(state),
        },
    }


# ============================================================================
# EVIDENCE PACK INTEGRATION (from BRAVO COMMAND)
# ============================================================================


def get_evidence_source(source_id: str) -> Optional[dict]:
    """Get an evidence source for citation purposes."""
    con = connect()
    cur = execute(
        con,
        """
        SELECT
            source_id, source_type, title, date_published, date_accessed, url,
            fr_citation, fr_doc_number, bill_number, bill_congress, report_number,
            issuing_agency, document_type
        FROM evidence_sources
        WHERE source_id = :source_id
        """,
        {"source_id": source_id},
    )
    row = cur.fetchone()
    con.close()

    if not row:
        return None

    return {
        "source_id": row[0],
        "source_type": row[1],
        "title": row[2],
        "date_published": row[3],
        "date_accessed": row[4],
        "url": row[5],
        "fr_citation": row[6],
        "fr_doc_number": row[7],
        "bill_number": row[8],
        "bill_congress": row[9],
        "report_number": row[10],
        "issuing_agency": row[11],
        "document_type": row[12],
    }


def find_evidence_for_source(source_type: str, source_id: str) -> Optional[dict]:
    """
    Find an evidence source matching the given source.

    Tries multiple matching strategies based on source type.
    """
    con = connect()

    # Try exact source_id match first
    cur = execute(
        con,
        "SELECT source_id FROM evidence_sources WHERE source_id = :source_id",
        {"source_id": source_id},
    )
    if cur.fetchone():
        con.close()
        return get_evidence_source(source_id)

    # Try type-specific matching
    if source_type == "federal_register":
        cur = execute(
            con,
            "SELECT source_id FROM evidence_sources WHERE fr_doc_number = :doc_num",
            {"doc_num": source_id},
        )
    elif source_type == "bill":
        # source_id format: "118hr1234" or "hr1234-118"
        cur = execute(
            con,
            "SELECT source_id FROM evidence_sources WHERE bill_number = :bill_num",
            {"bill_num": source_id},
        )
    elif source_type in ("oversight", "gao", "oig", "crs"):
        cur = execute(
            con,
            "SELECT source_id FROM evidence_sources WHERE report_number = :report_num",
            {"report_num": source_id},
        )
    else:
        con.close()
        return None

    row = cur.fetchone()
    con.close()

    if row:
        return get_evidence_source(row[0])
    return None
