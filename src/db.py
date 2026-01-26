import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "signals.db"
SCHEMA_PATH = ROOT / "schema.sql"
SCHEMA_POSTGRES_PATH = ROOT / "schema.postgres.sql"

_NAMED_PARAM_RE = re.compile(r"(?<!:):([a-zA-Z_][a-zA-Z0-9_]*)")


def _is_postgres() -> bool:
  return get_db_backend() == "postgres"


def _prepare_query(sql: str, params: Mapping[str, Any] | Sequence[Any] | None):
  """
  Normalize parameter style for the active backend.
  - SQLite: accepts :name or ? placeholders as-is.
  - Postgres (psycopg): translate :name -> %(name)s and ? -> %s.
  """
  if params is None or not _is_postgres():
    return sql, params

  if isinstance(params, Mapping):
    return _NAMED_PARAM_RE.sub(r"%(\1)s", sql), params

  return sql.replace("?", "%s"), params


def execute(con, sql: str, params: Mapping[str, Any] | Sequence[Any] | None = None):
  cur = con.cursor()
  sql, params = _prepare_query(sql, params)
  if params is None:
    cur.execute(sql)
  else:
    cur.execute(sql, params)
  return cur


def executemany(
  con,
  sql: str,
  params_seq: Iterable[Mapping[str, Any]] | Iterable[Sequence[Any]],
):
  cur = con.cursor()
  params_list = list(params_seq)
  if not params_list:
    return cur
  sql, _ = _prepare_query(sql, params_list[0])
  cur.executemany(sql, params_list)
  return cur


def table_exists(con, table_name: str) -> bool:
  if _is_postgres():
    cur = execute(con, "SELECT to_regclass(:table_name)", {"table_name": table_name})
    row = cur.fetchone()
    return row is not None and row[0] is not None
  cur = execute(
    con,
    "SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name",
    {"table_name": table_name},
  )
  return cur.fetchone() is not None


def insert_returning_id(con, sql: str, params: Mapping[str, Any], id_column: str = "id"):
  if _is_postgres():
    cur = execute(con, f"{sql} RETURNING {id_column}", params)
    row = cur.fetchone()
    return row[0] if row else None
  cur = execute(con, sql, params)
  return cur.lastrowid

def get_db_backend() -> str:
  db_url = os.environ.get("DATABASE_URL", "").strip()
  if not db_url:
    return "sqlite"
  scheme = urlparse(db_url).scheme.lower()
  if scheme.startswith("postgres"):
    return "postgres"
  return "sqlite"

def get_schema_path() -> Path:
  if get_db_backend() == "postgres":
    return SCHEMA_POSTGRES_PATH
  return SCHEMA_PATH

def connect():
  if _is_postgres():
    db_url = os.environ.get("DATABASE_URL", "").strip()
    if not db_url:
      raise RuntimeError("DATABASE_URL must be set for Postgres backend.")
    try:
      import psycopg
    except ImportError as exc:
      raise RuntimeError("psycopg is required for Postgres support.") from exc
    return psycopg.connect(db_url)

  DB_PATH.parent.mkdir(parents=True, exist_ok=True)
  return sqlite3.connect(DB_PATH)

def init_db():
  con = connect()
  schema_sql = get_schema_path().read_text(encoding="utf-8")
  if _is_postgres():
    statements = [s.strip() for s in schema_sql.split(";") if s.strip()]
    cur = con.cursor()
    for statement in statements:
      cur.execute(statement)
    con.commit()
    con.close()
    return
  con.executescript(schema_sql)
  con.commit()
  con.close()

def insert_source_run(run_record: dict):
  con = connect()
  execute(
    con,
    """INSERT INTO source_runs(
         source_id, started_at, ended_at, status, records_fetched, errors_json
       ) VALUES (
         :source_id, :started_at, :ended_at, :status, :records_fetched, :errors_json
       )""",
    {
      "source_id": run_record["source_id"],
      "started_at": run_record["started_at"],
      "ended_at": run_record["ended_at"],
      "status": run_record["status"],
      "records_fetched": run_record["records_fetched"],
      "errors_json": json.dumps(run_record["errors"]),
    },
  )
  con.commit()
  con.close()

def upsert_fr_seen(doc_id: str, published_date: str, first_seen_at: str, source_url: str) -> bool:
    """
    Returns True if inserted (new), False if already existed.
    """
    con = connect()
    cur = execute(con, "SELECT doc_id FROM fr_seen WHERE doc_id = :doc_id", {"doc_id": doc_id})
    exists = cur.fetchone() is not None
    if not exists:
        execute(
            con,
            """INSERT INTO fr_seen(doc_id, published_date, first_seen_at, source_url)
               VALUES(:doc_id, :published_date, :first_seen_at, :source_url)""",
            {
                "doc_id": doc_id,
                "published_date": published_date,
                "first_seen_at": first_seen_at,
                "source_url": source_url,
            },
        )
        con.commit()
    con.close()
    return not exists


def get_existing_fr_doc_ids(doc_ids: list[str]) -> set[str]:
    """
    Return the subset of doc_ids that already exist in fr_seen.
    Uses batched queries for efficiency.
    """
    if not doc_ids:
        return set()
    con = connect()
    existing: set[str] = set()
    # SQLite parameter limit is ~999, batch if needed
    batch_size = 900
    for i in range(0, len(doc_ids), batch_size):
        batch = doc_ids[i : i + batch_size]
        placeholders = ",".join(f":doc_id_{idx}" for idx in range(len(batch)))
        params = {f"doc_id_{idx}": value for idx, value in enumerate(batch)}
        cur = execute(
            con,
            f"SELECT doc_id FROM fr_seen WHERE doc_id IN ({placeholders})",
            params,
        )
        existing.update(row[0] for row in cur.fetchall())
    con.close()
    return existing


def bulk_insert_fr_seen(docs: list[dict]) -> int:
    """
    Insert multiple fr_seen records in a single transaction.
    Each doc should have: doc_id, published_date, first_seen_at, source_url.
    Returns count of inserted rows.
    """
    if not docs:
        return 0
    con = connect()
    cur = executemany(
        con,
        """INSERT INTO fr_seen(doc_id, published_date, first_seen_at, source_url)
           VALUES(:doc_id, :published_date, :first_seen_at, :source_url)
           ON CONFLICT(doc_id) DO NOTHING""",
        docs,
    )
    inserted = cur.rowcount
    con.commit()
    con.close()
    return inserted

def assert_tables_exist():
  con = connect()
  required = {"source_runs", "fr_seen"}
  missing = {name for name in required if not table_exists(con, name)}
  con.close()
  if missing:
    raise RuntimeError(f"DB_SCHEMA_MISSING_TABLES: {sorted(missing)}")

def upsert_ecfr_seen(doc_id: str, last_modified: str, etag: str, first_seen_at: str, source_url: str) -> bool:
    """
    Returns True if inserted or changed; False if unchanged.
    Change detection is based on (last_modified, etag).
    """
    con = connect()
    cur = execute(
        con,
        "SELECT last_modified, etag FROM ecfr_seen WHERE doc_id = :doc_id",
        {"doc_id": doc_id},
    )
    row = cur.fetchone()

    if row is None:
        execute(
            con,
            """INSERT INTO ecfr_seen(doc_id, last_modified, etag, first_seen_at, source_url)
               VALUES(:doc_id, :last_modified, :etag, :first_seen_at, :source_url)""",
            {
                "doc_id": doc_id,
                "last_modified": last_modified,
                "etag": etag,
                "first_seen_at": first_seen_at,
                "source_url": source_url,
            },
        )
        con.commit()
        con.close()
        return True

    prev_last_modified, prev_etag = row[0], row[1]
    if (prev_last_modified != last_modified) or (prev_etag != etag):
        execute(
            con,
            """UPDATE ecfr_seen
               SET last_modified=:last_modified, etag=:etag, first_seen_at=:first_seen_at, source_url=:source_url
               WHERE doc_id=:doc_id""",
            {
                "doc_id": doc_id,
                "last_modified": last_modified,
                "etag": etag,
                "first_seen_at": first_seen_at,
                "source_url": source_url,
            },
        )
        con.commit()
        con.close()
        return True

    con.close()
    return False


# --- Agenda Drift helpers ---

def _utc_now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


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
    cur = executemany(
        con,
        """INSERT INTO ad_utterances(
             utterance_id, member_id, hearing_id, chunk_ix, content, spoken_at, ingested_at
           ) VALUES (
             :utterance_id, :member_id, :hearing_id, :chunk_ix, :content, :spoken_at, :ingested_at
           ) ON CONFLICT(utterance_id) DO NOTHING""",
        payload,
    )
    inserted = cur.rowcount
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


# --- VA Bills helpers ---

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


# --- VA Hearings helpers ---

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
    tracked_fields = ["status", "hearing_date", "hearing_time", "title", "location", "witnesses_json"]

    for field in tracked_fields:
        old_val = existing_dict.get(field)
        new_val = hearing.get(field)
        # Normalize None vs empty string comparison
        if old_val != new_val and not (old_val is None and new_val == "") and not (old_val == "" and new_val is None):
            changes.append({
                "field_changed": field,
                "old_value": old_val,
                "new_value": new_val,
            })

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
           ORDER BY COUNT(*) DESC"""
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
