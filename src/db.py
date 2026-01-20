import json, sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "signals.db"
SCHEMA_PATH = ROOT / "schema.sql"

def connect():
  DB_PATH.parent.mkdir(parents=True, exist_ok=True)
  return sqlite3.connect(DB_PATH)

def init_db():
  con = connect()
  con.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
  con.commit()
  con.close()

def insert_source_run(run_record: dict):
  con = connect()
  con.execute(
    "INSERT INTO source_runs(source_id,started_at,ended_at,status,records_fetched,errors_json) VALUES(?,?,?,?,?,?)",
    (
      run_record["source_id"],
      run_record["started_at"],
      run_record["ended_at"],
      run_record["status"],
      run_record["records_fetched"],
      json.dumps(run_record["errors"]),
    ),
  )
  con.commit()
  con.close()

def upsert_fr_seen(doc_id: str, published_date: str, first_seen_at: str, source_url: str) -> bool:
    """
    Returns True if inserted (new), False if already existed.
    """
    con = connect()
    cur = con.cursor()
    cur.execute("SELECT doc_id FROM fr_seen WHERE doc_id = ?", (doc_id,))
    exists = cur.fetchone() is not None
    if not exists:
        cur.execute(
            "INSERT INTO fr_seen(doc_id,published_date,first_seen_at,source_url) VALUES(?,?,?,?)",
            (doc_id, published_date, first_seen_at, source_url),
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
    cur = con.cursor()
    existing: set[str] = set()
    # SQLite parameter limit is ~999, batch if needed
    batch_size = 900
    for i in range(0, len(doc_ids), batch_size):
        batch = doc_ids[i : i + batch_size]
        placeholders = ",".join("?" * len(batch))
        cur.execute(f"SELECT doc_id FROM fr_seen WHERE doc_id IN ({placeholders})", batch)
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
    cur = con.cursor()
    cur.executemany(
        "INSERT OR IGNORE INTO fr_seen(doc_id,published_date,first_seen_at,source_url) VALUES(?,?,?,?)",
        [(d["doc_id"], d["published_date"], d["first_seen_at"], d["source_url"]) for d in docs],
    )
    inserted = cur.rowcount
    con.commit()
    con.close()
    return inserted

def assert_tables_exist():
  con = connect()
  rows = con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
  con.close()
  names = {r[0] for r in rows}
  missing = {"source_runs","fr_seen"} - names
  if missing:
    raise RuntimeError(f"DB_SCHEMA_MISSING_TABLES: {sorted(missing)}")

def upsert_ecfr_seen(doc_id: str, last_modified: str, etag: str, first_seen_at: str, source_url: str) -> bool:
    """
    Returns True if inserted or changed; False if unchanged.
    Change detection is based on (last_modified, etag).
    """
    con = connect()
    cur = con.cursor()
    cur.execute("SELECT last_modified, etag FROM ecfr_seen WHERE doc_id = ?", (doc_id,))
    row = cur.fetchone()

    if row is None:
        cur.execute(
            "INSERT INTO ecfr_seen(doc_id,last_modified,etag,first_seen_at,source_url) VALUES(?,?,?,?,?)",
            (doc_id, last_modified, etag, first_seen_at, source_url),
        )
        con.commit()
        con.close()
        return True

    prev_last_modified, prev_etag = row[0], row[1]
    if (prev_last_modified != last_modified) or (prev_etag != etag):
        cur.execute(
            "UPDATE ecfr_seen SET last_modified=?, etag=?, first_seen_at=?, source_url=? WHERE doc_id=?",
            (last_modified, etag, first_seen_at, source_url, doc_id),
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
    cur = con.cursor()
    cur.execute("SELECT member_id FROM ad_members WHERE member_id = ?", (member_id,))
    exists = cur.fetchone() is not None
    if not exists:
        cur.execute(
            "INSERT INTO ad_members(member_id, name, party, committee, created_at) VALUES(?,?,?,?,?)",
            (member_id, name, party, committee, _utc_now_iso()),
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
    cur = con.cursor()
    now = _utc_now_iso()
    cur.executemany(
        "INSERT OR IGNORE INTO ad_utterances(utterance_id, member_id, hearing_id, chunk_ix, content, spoken_at, ingested_at) VALUES(?,?,?,?,?,?,?)",
        [
            (u["utterance_id"], u["member_id"], u["hearing_id"], u.get("chunk_ix", 0), u["content"], u["spoken_at"], now)
            for u in utterances
        ],
    )
    inserted = cur.rowcount
    con.commit()
    con.close()
    return inserted


def get_ad_utterances_for_member(member_id: str, limit: int = 500) -> list[dict]:
    """Get recent utterances for baseline building."""
    con = connect()
    cur = con.cursor()
    cur.execute(
        """SELECT utterance_id, hearing_id, chunk_ix, content, spoken_at
           FROM ad_utterances WHERE member_id = ?
           ORDER BY spoken_at DESC LIMIT ?""",
        (member_id, limit),
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
    cur = con.cursor()
    cur.execute("SELECT utterance_id FROM ad_embeddings WHERE utterance_id = ?", (utterance_id,))
    exists = cur.fetchone() is not None
    vec_json = json.dumps(vec)
    now = _utc_now_iso()
    if not exists:
        cur.execute(
            "INSERT INTO ad_embeddings(utterance_id, vec, model_id, embedded_at) VALUES(?,?,?,?)",
            (utterance_id, vec_json, model_id, now),
        )
    else:
        cur.execute(
            "UPDATE ad_embeddings SET vec=?, model_id=?, embedded_at=? WHERE utterance_id=?",
            (vec_json, model_id, now, utterance_id),
        )
    con.commit()
    con.close()
    return not exists


def get_ad_embeddings_for_member(member_id: str) -> list[tuple[str, list[float]]]:
    """Get all embeddings for a member's utterances. Returns [(utterance_id, vec), ...]."""
    con = connect()
    cur = con.cursor()
    cur.execute(
        """SELECT e.utterance_id, e.vec
           FROM ad_embeddings e
           JOIN ad_utterances u ON e.utterance_id = u.utterance_id
           WHERE u.member_id = ?""",
        (member_id,),
    )
    rows = cur.fetchall()
    con.close()
    return [(r[0], json.loads(r[1])) for r in rows]


def insert_ad_baseline(member_id: str, vec_mean: list[float], mu: float, sigma: float, n: int) -> int:
    """Insert baseline, return id."""
    con = connect()
    cur = con.cursor()
    cur.execute(
        "INSERT INTO ad_baselines(member_id, built_at, vec_mean, mu, sigma, n) VALUES(?,?,?,?,?,?)",
        (member_id, _utc_now_iso(), json.dumps(vec_mean), mu, sigma, n),
    )
    baseline_id = cur.lastrowid
    con.commit()
    con.close()
    return baseline_id


def get_latest_ad_baseline(member_id: str) -> dict | None:
    """Get most recent baseline for member."""
    con = connect()
    cur = con.cursor()
    cur.execute(
        """SELECT id, built_at, vec_mean, mu, sigma, n
           FROM ad_baselines WHERE member_id = ?
           ORDER BY built_at DESC LIMIT 1""",
        (member_id,),
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
    cur = con.cursor()
    cur.execute(
        """INSERT INTO ad_deviation_events(member_id, hearing_id, utterance_id, baseline_id, cos_dist, zscore, detected_at, note)
           VALUES(?,?,?,?,?,?,?,?)""",
        (
            event["member_id"],
            event["hearing_id"],
            event["utterance_id"],
            event["baseline_id"],
            event["cos_dist"],
            event["zscore"],
            event.get("detected_at", _utc_now_iso()),
            event.get("note"),
        ),
    )
    event_id = cur.lastrowid
    con.commit()
    con.close()
    return event_id


def get_ad_deviation_events(limit: int = 50, min_zscore: float = 0) -> list[dict]:
    """Query recent deviation events with member names."""
    con = connect()
    cur = con.cursor()
    cur.execute(
        """SELECT e.id, e.member_id, m.name, e.hearing_id, e.utterance_id, e.baseline_id,
                  e.cos_dist, e.zscore, e.detected_at, e.note
           FROM ad_deviation_events e
           JOIN ad_members m ON e.member_id = m.member_id
           WHERE e.zscore >= ?
           ORDER BY e.detected_at DESC LIMIT ?""",
        (min_zscore, limit),
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
    cur = con.cursor()
    cur.execute(
        """SELECT e.id, e.hearing_id, e.utterance_id, e.cos_dist, e.zscore, e.detected_at, e.note
           FROM ad_deviation_events e
           WHERE e.member_id = ?
           ORDER BY e.detected_at DESC LIMIT ?""",
        (member_id, limit),
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
    cur = con.cursor()
    cur.execute(
        """SELECT cos_dist, zscore FROM ad_deviation_events
           WHERE member_id = ? AND hearing_id = ?
           ORDER BY detected_at DESC LIMIT ?""",
        (member_id, hearing_id, limit),
    )
    rows = cur.fetchall()
    con.close()
    return [{"cos_dist": r[0], "zscore": r[1]} for r in rows]
