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
