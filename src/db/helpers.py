"""Shared helper functions for the db package."""

import json

from .core import connect, execute


def _utc_now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


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
