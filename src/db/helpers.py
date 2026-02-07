"""Shared helper functions for the db package."""

import json
import logging

from .core import connect, execute

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def insert_source_run(run_record: dict):
  source_id = run_record.get("source_id", "")
  started_at = run_record.get("started_at", "")
  if len(source_id) <= 1 or len(started_at) <= 1:
      logger.warning(
          "Skipping source_run with invalid data: source_id=%r started_at=%r",
          source_id, started_at,
      )
      return

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
