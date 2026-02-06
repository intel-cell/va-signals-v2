"""Bills database functions."""

from typing import Any

from .core import connect, execute
from .helpers import _utc_now_iso


def upsert_bill(bill: dict) -> bool:
    """
    Insert or update a bill. Returns True if new (inserted), False if updated.
    Expected keys: bill_id, congress, bill_type, bill_number, title,
    sponsor_name, sponsor_bioguide_id, sponsor_party, sponsor_state,
    introduced_date, latest_action_date, latest_action_text, policy_area,
    committees_json, cosponsors_count.
    """
    con = connect()
    now = _utc_now_iso()
    cur = execute(con, "SELECT bill_id FROM bills WHERE bill_id = :bill_id", {"bill_id": bill["bill_id"]})
    exists = cur.fetchone() is not None

    if not exists:
        execute(
            con,
            """INSERT INTO bills(bill_id, congress, bill_type, bill_number, title,
               sponsor_name, sponsor_bioguide_id, sponsor_party, sponsor_state,
               introduced_date, latest_action_date, latest_action_text, policy_area,
               committees_json, cosponsors_count, first_seen_at, updated_at)
               VALUES(:bill_id, :congress, :bill_type, :bill_number, :title,
                      :sponsor_name, :sponsor_bioguide_id, :sponsor_party, :sponsor_state,
                      :introduced_date, :latest_action_date, :latest_action_text, :policy_area,
                      :committees_json, :cosponsors_count, :first_seen_at, :updated_at)""",
            {
                "bill_id": bill["bill_id"],
                "congress": bill["congress"],
                "bill_type": bill["bill_type"],
                "bill_number": bill["bill_number"],
                "title": bill["title"],
                "sponsor_name": bill.get("sponsor_name"),
                "sponsor_bioguide_id": bill.get("sponsor_bioguide_id"),
                "sponsor_party": bill.get("sponsor_party"),
                "sponsor_state": bill.get("sponsor_state"),
                "introduced_date": bill.get("introduced_date"),
                "latest_action_date": bill.get("latest_action_date"),
                "latest_action_text": bill.get("latest_action_text"),
                "policy_area": bill.get("policy_area"),
                "committees_json": bill.get("committees_json"),
                "cosponsors_count": bill.get("cosponsors_count", 0),
                "first_seen_at": now,
                "updated_at": now,
            },
        )
    else:
        execute(
            con,
            """UPDATE bills SET congress=:congress, bill_type=:bill_type, bill_number=:bill_number, title=:title,
               sponsor_name=:sponsor_name, sponsor_bioguide_id=:sponsor_bioguide_id, sponsor_party=:sponsor_party, sponsor_state=:sponsor_state,
               introduced_date=:introduced_date, latest_action_date=:latest_action_date, latest_action_text=:latest_action_text, policy_area=:policy_area,
               committees_json=:committees_json, cosponsors_count=:cosponsors_count, updated_at=:updated_at
               WHERE bill_id=:bill_id""",
            {
                "bill_id": bill["bill_id"],
                "congress": bill["congress"],
                "bill_type": bill["bill_type"],
                "bill_number": bill["bill_number"],
                "title": bill["title"],
                "sponsor_name": bill.get("sponsor_name"),
                "sponsor_bioguide_id": bill.get("sponsor_bioguide_id"),
                "sponsor_party": bill.get("sponsor_party"),
                "sponsor_state": bill.get("sponsor_state"),
                "introduced_date": bill.get("introduced_date"),
                "latest_action_date": bill.get("latest_action_date"),
                "latest_action_text": bill.get("latest_action_text"),
                "policy_area": bill.get("policy_area"),
                "committees_json": bill.get("committees_json"),
                "cosponsors_count": bill.get("cosponsors_count", 0),
                "updated_at": now,
            },
        )
    con.commit()
    con.close()
    return not exists


def get_bill(bill_id: str) -> dict | None:
    """Get a single bill by ID."""
    con = connect()
    cur = execute(
        con,
        """SELECT bill_id, congress, bill_type, bill_number, title,
           sponsor_name, sponsor_bioguide_id, sponsor_party, sponsor_state,
           introduced_date, latest_action_date, latest_action_text, policy_area,
           committees_json, cosponsors_count, first_seen_at, updated_at
           FROM bills WHERE bill_id = :bill_id""",
        {"bill_id": bill_id},
    )
    row = cur.fetchone()
    con.close()
    if not row:
        return None
    return {
        "bill_id": row[0],
        "congress": row[1],
        "bill_type": row[2],
        "bill_number": row[3],
        "title": row[4],
        "sponsor_name": row[5],
        "sponsor_bioguide_id": row[6],
        "sponsor_party": row[7],
        "sponsor_state": row[8],
        "introduced_date": row[9],
        "latest_action_date": row[10],
        "latest_action_text": row[11],
        "policy_area": row[12],
        "committees_json": row[13],
        "cosponsors_count": row[14],
        "first_seen_at": row[15],
        "updated_at": row[16],
    }


def get_bills(limit: int = 50, congress: int = None) -> list[dict]:
    """Get bills, optionally filtered by congress."""
    con = connect()
    if congress is not None:
        cur = execute(
            con,
            """SELECT bill_id, congress, bill_type, bill_number, title,
               sponsor_name, sponsor_bioguide_id, sponsor_party, sponsor_state,
               introduced_date, latest_action_date, latest_action_text, policy_area,
               committees_json, cosponsors_count, first_seen_at, updated_at
               FROM bills WHERE congress = :congress
               ORDER BY latest_action_date DESC LIMIT :limit""",
            {"congress": congress, "limit": limit},
        )
    else:
        cur = execute(
            con,
            """SELECT bill_id, congress, bill_type, bill_number, title,
               sponsor_name, sponsor_bioguide_id, sponsor_party, sponsor_state,
               introduced_date, latest_action_date, latest_action_text, policy_area,
               committees_json, cosponsors_count, first_seen_at, updated_at
               FROM bills ORDER BY latest_action_date DESC LIMIT :limit""",
            {"limit": limit},
        )
    rows = cur.fetchall()
    con.close()
    return [
        {
            "bill_id": r[0],
            "congress": r[1],
            "bill_type": r[2],
            "bill_number": r[3],
            "title": r[4],
            "sponsor_name": r[5],
            "sponsor_bioguide_id": r[6],
            "sponsor_party": r[7],
            "sponsor_state": r[8],
            "introduced_date": r[9],
            "latest_action_date": r[10],
            "latest_action_text": r[11],
            "policy_area": r[12],
            "committees_json": r[13],
            "cosponsors_count": r[14],
            "first_seen_at": r[15],
            "updated_at": r[16],
        }
        for r in rows
    ]


def insert_bill_action(bill_id: str, action: dict) -> bool:
    """
    Insert a bill action. Returns True if new (inserted), False if already exists.
    Expected action keys: action_date, action_text, action_type (optional).
    """
    con = connect()
    now = _utc_now_iso()
    cur = execute(
        con,
        """INSERT INTO bill_actions(bill_id, action_date, action_text, action_type, first_seen_at)
           VALUES(:bill_id, :action_date, :action_text, :action_type, :first_seen_at)
           ON CONFLICT(bill_id, action_date, action_text) DO NOTHING""",
        {
            "bill_id": bill_id,
            "action_date": action["action_date"],
            "action_text": action["action_text"],
            "action_type": action.get("action_type"),
            "first_seen_at": now,
        },
    )
    con.commit()
    con.close()
    return cur.rowcount > 0


def get_bill_actions(bill_id: str) -> list[dict]:
    """Get all actions for a bill, ordered by date descending."""
    con = connect()
    cur = execute(
        con,
        """SELECT id, bill_id, action_date, action_text, action_type, first_seen_at
           FROM bill_actions WHERE bill_id = :bill_id
           ORDER BY action_date DESC, id DESC""",
        {"bill_id": bill_id},
    )
    rows = cur.fetchall()
    con.close()
    return [
        {
            "id": r[0],
            "bill_id": r[1],
            "action_date": r[2],
            "action_text": r[3],
            "action_type": r[4],
            "first_seen_at": r[5],
        }
        for r in rows
    ]


def get_new_bills_since(since: str) -> list[dict]:
    """Get bills first seen after the given ISO timestamp."""
    con = connect()
    cur = execute(
        con,
        """SELECT bill_id, congress, bill_type, bill_number, title,
           sponsor_name, sponsor_bioguide_id, sponsor_party, sponsor_state,
           introduced_date, latest_action_date, latest_action_text, policy_area,
           committees_json, cosponsors_count, first_seen_at, updated_at
           FROM bills WHERE first_seen_at > :since
           ORDER BY first_seen_at DESC""",
        {"since": since},
    )
    rows = cur.fetchall()
    con.close()
    return [
        {
            "bill_id": r[0],
            "congress": r[1],
            "bill_type": r[2],
            "bill_number": r[3],
            "title": r[4],
            "sponsor_name": r[5],
            "sponsor_bioguide_id": r[6],
            "sponsor_party": r[7],
            "sponsor_state": r[8],
            "introduced_date": r[9],
            "latest_action_date": r[10],
            "latest_action_text": r[11],
            "policy_area": r[12],
            "committees_json": r[13],
            "cosponsors_count": r[14],
            "first_seen_at": r[15],
            "updated_at": r[16],
        }
        for r in rows
    ]


def get_new_actions_since(since: str) -> list[dict]:
    """Get bill actions first seen after the given ISO timestamp."""
    con = connect()
    cur = execute(
        con,
        """SELECT a.id, a.bill_id, a.action_date, a.action_text, a.action_type, a.first_seen_at,
           b.title, b.congress, b.bill_type, b.bill_number
           FROM bill_actions a
           JOIN bills b ON a.bill_id = b.bill_id
           WHERE a.first_seen_at > :since
           ORDER BY a.first_seen_at DESC""",
        {"since": since},
    )
    rows = cur.fetchall()
    con.close()
    return [
        {
            "id": r[0],
            "bill_id": r[1],
            "action_date": r[2],
            "action_text": r[3],
            "action_type": r[4],
            "first_seen_at": r[5],
            "bill_title": r[6],
            "congress": r[7],
            "bill_type": r[8],
            "bill_number": r[9],
        }
        for r in rows
    ]


def get_bill_stats() -> dict:
    """Get summary statistics for bills tracking."""
    con = connect()
    cur = con.cursor()

    # Total bills
    cur = execute(con, "SELECT COUNT(*) FROM bills")
    total_bills = cur.fetchone()[0]

    # Bills by congress
    cur = execute(con, "SELECT congress, COUNT(*) FROM bills GROUP BY congress ORDER BY congress DESC")
    by_congress = {r[0]: r[1] for r in cur.fetchall()}

    # Total actions
    cur = execute(con, "SELECT COUNT(*) FROM bill_actions")
    total_actions = cur.fetchone()[0]

    # Bills by party
    cur = execute(
        con,
        "SELECT sponsor_party, COUNT(*) FROM bills WHERE sponsor_party IS NOT NULL GROUP BY sponsor_party",
    )
    by_party = {r[0]: r[1] for r in cur.fetchall()}

    # Most recent bill
    cur = execute(
        con,
        "SELECT bill_id, title, latest_action_date FROM bills ORDER BY latest_action_date DESC LIMIT 1",
    )
    row = cur.fetchone()
    most_recent = {"bill_id": row[0], "title": row[1], "latest_action_date": row[2]} if row else None

    con.close()
    return {
        "total_bills": total_bills,
        "by_congress": by_congress,
        "total_actions": total_actions,
        "by_party": by_party,
        "most_recent": most_recent,
    }
