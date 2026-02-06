"""Agenda Drift database functions."""

import json

from .core import connect, execute, insert_returning_id, _count_inserted_rows
from .helpers import _utc_now_iso


def upsert_ad_member(member_id: str, name: str, party: str = None, committee: str = None) -> bool:
    """Insert or update member. Returns True if new."""
    con = connect()
    cur = execute(con, "SELECT member_id FROM ad_members WHERE member_id = :member_id", {"member_id": member_id})
    exists = cur.fetchone() is not None
    if not exists:
        execute(
            con,
            """INSERT INTO ad_members(member_id, name, party, committee, created_at)
               VALUES(:member_id, :name, :party, :committee, :created_at)""",
            {
                "member_id": member_id,
                "name": name,
                "party": party,
                "committee": committee,
                "created_at": _utc_now_iso(),
            },
        )
        con.commit()
    con.close()
    return not exists


def bulk_insert_ad_utterances(utterances: list[dict]) -> int:
    """
    Insert utterances. Each dict: utterance_id, member_id, hearing_id, chunk_ix, content, spoken_at.
    Returns count inserted.
    """
    if not utterances:
        return 0
    con = connect()
    now = _utc_now_iso()
    payload = [
        {
            "utterance_id": u["utterance_id"],
            "member_id": u["member_id"],
            "hearing_id": u["hearing_id"],
            "chunk_ix": u.get("chunk_ix", 0),
            "content": u["content"],
            "spoken_at": u["spoken_at"],
            "ingested_at": now,
        }
        for u in utterances
    ]
    inserted = _count_inserted_rows(
        con,
        """INSERT INTO ad_utterances(
             utterance_id, member_id, hearing_id, chunk_ix, content, spoken_at, ingested_at
           ) VALUES (
             :utterance_id, :member_id, :hearing_id, :chunk_ix, :content, :spoken_at, :ingested_at
           ) ON CONFLICT(utterance_id) DO NOTHING""",
        payload,
    )
    con.commit()
    con.close()
    return inserted


def get_ad_utterances_for_member(member_id: str, limit: int = 500) -> list[dict]:
    """Get recent utterances for baseline building."""
    con = connect()
    cur = execute(
        con,
        """SELECT utterance_id, hearing_id, chunk_ix, content, spoken_at
           FROM ad_utterances WHERE member_id = :member_id
           ORDER BY spoken_at DESC LIMIT :limit""",
        {"member_id": member_id, "limit": limit},
    )
    rows = cur.fetchall()
    con.close()
    return [
        {"utterance_id": r[0], "hearing_id": r[1], "chunk_ix": r[2], "content": r[3], "spoken_at": r[4]}
        for r in rows
    ]


def upsert_ad_embedding(utterance_id: str, vec: list[float], model_id: str) -> bool:
    """Store embedding vector as JSON. Returns True if new."""
    con = connect()
    cur = execute(
        con,
        "SELECT utterance_id FROM ad_embeddings WHERE utterance_id = :utterance_id",
        {"utterance_id": utterance_id},
    )
    exists = cur.fetchone() is not None
    vec_json = json.dumps(vec)
    now = _utc_now_iso()
    if not exists:
        execute(
            con,
            """INSERT INTO ad_embeddings(utterance_id, vec, model_id, embedded_at)
               VALUES(:utterance_id, :vec, :model_id, :embedded_at)""",
            {
                "utterance_id": utterance_id,
                "vec": vec_json,
                "model_id": model_id,
                "embedded_at": now,
            },
        )
    else:
        execute(
            con,
            """UPDATE ad_embeddings
               SET vec=:vec, model_id=:model_id, embedded_at=:embedded_at
               WHERE utterance_id=:utterance_id""",
            {
                "utterance_id": utterance_id,
                "vec": vec_json,
                "model_id": model_id,
                "embedded_at": now,
            },
        )
    con.commit()
    con.close()
    return not exists


def get_ad_embeddings_for_member(member_id: str, min_content_length: int = 100) -> list[tuple[str, list[float]]]:
    """Get all embeddings for a member's utterances. Returns [(utterance_id, vec), ...].

    Filters out short utterances (< min_content_length chars) to exclude
    procedural statements that would skew the baseline.
    """
    con = connect()
    cur = execute(
        con,
        """SELECT e.utterance_id, e.vec
           FROM ad_embeddings e
           JOIN ad_utterances u ON e.utterance_id = u.utterance_id
           WHERE u.member_id = :member_id AND LENGTH(u.content) >= :min_content_length""",
        {"member_id": member_id, "min_content_length": min_content_length},
    )
    rows = cur.fetchall()
    con.close()
    return [(r[0], json.loads(r[1])) for r in rows]


def insert_ad_baseline(member_id: str, vec_mean: list[float], mu: float, sigma: float, n: int) -> int:
    """Insert baseline, return id."""
    con = connect()
    baseline_id = insert_returning_id(
        con,
        """INSERT INTO ad_baselines(member_id, built_at, vec_mean, mu, sigma, n)
           VALUES(:member_id, :built_at, :vec_mean, :mu, :sigma, :n)""",
        {
            "member_id": member_id,
            "built_at": _utc_now_iso(),
            "vec_mean": json.dumps(vec_mean),
            "mu": mu,
            "sigma": sigma,
            "n": n,
        },
    )
    con.commit()
    con.close()
    return baseline_id


def get_latest_ad_baseline(member_id: str) -> dict | None:
    """Get most recent baseline for member."""
    con = connect()
    cur = execute(
        con,
        """SELECT id, built_at, vec_mean, mu, sigma, n
           FROM ad_baselines WHERE member_id = :member_id
           ORDER BY built_at DESC LIMIT 1""",
        {"member_id": member_id},
    )
    row = cur.fetchone()
    con.close()
    if not row:
        return None
    return {
        "id": row[0],
        "member_id": member_id,
        "built_at": row[1],
        "vec_mean": json.loads(row[2]),
        "mu": row[3],
        "sigma": row[4],
        "n": row[5],
    }


def insert_ad_deviation_event(event: dict) -> int:
    """Insert deviation event, return id."""
    con = connect()
    event_id = insert_returning_id(
        con,
        """INSERT INTO ad_deviation_events(
             member_id, hearing_id, utterance_id, baseline_id, cos_dist, zscore, detected_at, note
           ) VALUES (
             :member_id, :hearing_id, :utterance_id, :baseline_id, :cos_dist, :zscore, :detected_at, :note
           )""",
        {
            "member_id": event["member_id"],
            "hearing_id": event["hearing_id"],
            "utterance_id": event["utterance_id"],
            "baseline_id": event["baseline_id"],
            "cos_dist": event["cos_dist"],
            "zscore": event["zscore"],
            "detected_at": event.get("detected_at", _utc_now_iso()),
            "note": event.get("note"),
        },
    )
    con.commit()
    con.close()
    return event_id


def get_ad_deviation_events(limit: int = 50, min_zscore: float = 0) -> list[dict]:
    """Query recent deviation events with member names."""
    con = connect()
    cur = execute(
        con,
        """SELECT e.id, e.member_id, m.name, e.hearing_id, e.utterance_id, e.baseline_id,
                  e.cos_dist, e.zscore, e.detected_at, e.note
           FROM ad_deviation_events e
           JOIN ad_members m ON e.member_id = m.member_id
           WHERE e.zscore >= :min_zscore
           ORDER BY e.detected_at DESC LIMIT :limit""",
        {"min_zscore": min_zscore, "limit": limit},
    )
    rows = cur.fetchall()
    con.close()
    return [
        {
            "id": r[0],
            "member_id": r[1],
            "member_name": r[2],
            "hearing_id": r[3],
            "utterance_id": r[4],
            "baseline_id": r[5],
            "cos_dist": r[6],
            "zscore": r[7],
            "detected_at": r[8],
            "note": r[9],
        }
        for r in rows
    ]


def get_ad_member_deviation_history(member_id: str, limit: int = 20) -> list[dict]:
    """Get deviation history for a specific member."""
    con = connect()
    cur = execute(
        con,
        """SELECT e.id, e.hearing_id, e.utterance_id, e.cos_dist, e.zscore, e.detected_at, e.note
           FROM ad_deviation_events e
           WHERE e.member_id = :member_id
           ORDER BY e.detected_at DESC LIMIT :limit""",
        {"member_id": member_id, "limit": limit},
    )
    rows = cur.fetchall()
    con.close()
    return [
        {
            "id": r[0],
            "hearing_id": r[1],
            "utterance_id": r[2],
            "cos_dist": r[3],
            "zscore": r[4],
            "detected_at": r[5],
            "note": r[6],
        }
        for r in rows
    ]


def get_ad_recent_deviations_for_hearing(member_id: str, hearing_id: str, limit: int = 8) -> list[dict]:
    """Get recent deviations for K-of-M debounce check."""
    con = connect()
    cur = execute(
        con,
        """SELECT cos_dist, zscore FROM ad_deviation_events
           WHERE member_id = :member_id AND hearing_id = :hearing_id
           ORDER BY detected_at DESC LIMIT :limit""",
        {"member_id": member_id, "hearing_id": hearing_id, "limit": limit},
    )
    rows = cur.fetchall()
    con.close()
    return [{"cos_dist": r[0], "zscore": r[1]} for r in rows]


def get_ad_utterance_by_id(utterance_id: str) -> dict | None:
    """Get a single utterance by ID."""
    con = connect()
    cur = execute(
        con,
        """SELECT u.utterance_id, u.member_id, u.hearing_id, u.content, u.spoken_at, m.name
           FROM ad_utterances u
           JOIN ad_members m ON u.member_id = m.member_id
           WHERE u.utterance_id = :utterance_id""",
        {"utterance_id": utterance_id},
    )
    row = cur.fetchone()
    con.close()
    if not row:
        return None
    return {
        "utterance_id": row[0],
        "member_id": row[1],
        "hearing_id": row[2],
        "content": row[3],
        "spoken_at": row[4],
        "member_name": row[5],
    }


def get_ad_typical_utterances(member_id: str, exclude_utterance_id: str = None, limit: int = 5) -> list[dict]:
    """
    Get typical utterances for a member (ones closest to their baseline centroid).
    Excludes the specified utterance if provided.
    Returns utterances with their content for LLM comparison.
    """
    con = connect()

    # Get utterances that have embeddings and are NOT flagged as deviations
    # This gives us "normal" utterances for the member
    if exclude_utterance_id:
        cur = execute(
            con,
            """SELECT u.utterance_id, u.content, u.spoken_at
               FROM ad_utterances u
               JOIN ad_embeddings e ON u.utterance_id = e.utterance_id
               LEFT JOIN ad_deviation_events d ON u.utterance_id = d.utterance_id
               WHERE u.member_id = :member_id AND u.utterance_id != :exclude_utterance_id AND d.id IS NULL
               ORDER BY u.spoken_at DESC LIMIT :limit""",
            {
                "member_id": member_id,
                "exclude_utterance_id": exclude_utterance_id,
                "limit": limit,
            },
        )
    else:
        cur = execute(
            con,
            """SELECT u.utterance_id, u.content, u.spoken_at
               FROM ad_utterances u
               JOIN ad_embeddings e ON u.utterance_id = e.utterance_id
               LEFT JOIN ad_deviation_events d ON u.utterance_id = d.utterance_id
               WHERE u.member_id = :member_id AND d.id IS NULL
               ORDER BY u.spoken_at DESC LIMIT :limit""",
            {"member_id": member_id, "limit": limit},
        )

    rows = cur.fetchall()
    con.close()
    return [
        {"utterance_id": row[0], "content": row[1], "spoken_at": row[2]}
        for row in rows
    ]


def update_ad_deviation_note(event_id: int, note: str) -> None:
    """Update the note field for a deviation event."""
    con = connect()
    execute(
        con,
        "UPDATE ad_deviation_events SET note = :note WHERE id = :event_id",
        {"note": note, "event_id": event_id},
    )
    con.commit()
    con.close()


def get_ad_deviations_without_notes(limit: int = 50) -> list[dict]:
    """Get deviation events that don't have explanations yet."""
    con = connect()
    cur = execute(
        con,
        """SELECT e.id, e.member_id, m.name, e.hearing_id, e.utterance_id, e.zscore
           FROM ad_deviation_events e
           JOIN ad_members m ON e.member_id = m.member_id
           WHERE e.note IS NULL OR e.note = ''
           ORDER BY e.detected_at DESC LIMIT :limit""",
        {"limit": limit},
    )
    rows = cur.fetchall()
    con.close()
    return [
        {
            "id": r[0],
            "member_id": r[1],
            "member_name": r[2],
            "hearing_id": r[3],
            "utterance_id": r[4],
            "zscore": r[5],
        }
        for r in rows
    ]
