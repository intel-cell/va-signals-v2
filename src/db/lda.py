"""LDA Lobbying Disclosure database functions."""

from .core import connect, execute


def upsert_lda_filing(filing: dict) -> bool:
    """
    Insert or skip an LDA filing (filing_uuid is PK).

    Returns:
        True if new filing inserted, False if already existed
    """
    con = connect()
    try:
        cur = execute(
            con,
            "SELECT filing_uuid FROM lda_filings WHERE filing_uuid = :filing_uuid",
            {"filing_uuid": filing["filing_uuid"]},
        )
        if cur.fetchone():
            con.close()
            return False

        execute(
            con,
            """INSERT INTO lda_filings (
                filing_uuid, filing_type, filing_year, filing_period,
                dt_posted, registrant_name, registrant_id, client_name, client_id,
                income_amount, expense_amount, lobbying_issues_json,
                specific_issues_text, govt_entities_json, lobbyists_json,
                foreign_entity_listed, foreign_entities_json, covered_positions_json,
                source_url, first_seen_at, updated_at,
                va_relevance_score, va_relevance_reason
            ) VALUES (
                :filing_uuid, :filing_type, :filing_year, :filing_period,
                :dt_posted, :registrant_name, :registrant_id, :client_name, :client_id,
                :income_amount, :expense_amount, :lobbying_issues_json,
                :specific_issues_text, :govt_entities_json, :lobbyists_json,
                :foreign_entity_listed, :foreign_entities_json, :covered_positions_json,
                :source_url, :first_seen_at, :updated_at,
                :va_relevance_score, :va_relevance_reason
            )""",
            filing,
        )
        con.commit()
        return True
    finally:
        con.close()


def insert_lda_alert(alert: dict) -> int:
    """
    Insert an LDA alert.

    Returns:
        Auto-generated alert ID
    """
    con = connect()
    cur = execute(
        con,
        """INSERT INTO lda_alerts (
            filing_uuid, alert_type, severity, summary, details_json, created_at
        ) VALUES (
            :filing_uuid, :alert_type, :severity, :summary, :details_json, :created_at
        )""",
        alert,
    )
    con.commit()
    alert_id = cur.lastrowid
    con.close()
    return alert_id


def get_new_lda_filings_since(since: str) -> list[dict]:
    """Get LDA filings first seen since a given ISO datetime."""
    con = connect()
    cur = execute(
        con,
        """SELECT filing_uuid, filing_type, dt_posted, registrant_name, client_name,
                  va_relevance_score, va_relevance_reason, source_url, first_seen_at
           FROM lda_filings
           WHERE first_seen_at >= :since
           ORDER BY first_seen_at DESC""",
        {"since": since},
    )
    rows = cur.fetchall()
    con.close()
    return [
        {
            "filing_uuid": r[0],
            "filing_type": r[1],
            "dt_posted": r[2],
            "registrant_name": r[3],
            "client_name": r[4],
            "va_relevance_score": r[5],
            "va_relevance_reason": r[6],
            "source_url": r[7],
            "first_seen_at": r[8],
        }
        for r in rows
    ]


def get_lda_stats() -> dict:
    """Get LDA filing statistics."""
    con = connect()

    cur = execute(con, "SELECT COUNT(*) FROM lda_filings")
    total = cur.fetchone()[0]

    cur = execute(
        con,
        "SELECT filing_type, COUNT(*) FROM lda_filings GROUP BY filing_type",
    )
    by_type = dict(cur.fetchall())

    cur = execute(
        con,
        "SELECT va_relevance_score, COUNT(*) FROM lda_filings GROUP BY va_relevance_score",
    )
    by_relevance = dict(cur.fetchall())

    cur = execute(
        con,
        "SELECT COUNT(*) FROM lda_alerts WHERE acknowledged = 0",
    )
    unacknowledged = cur.fetchone()[0]

    con.close()
    return {
        "total_filings": total,
        "by_type": by_type,
        "by_relevance": by_relevance,
        "unacknowledged_alerts": unacknowledged,
    }
