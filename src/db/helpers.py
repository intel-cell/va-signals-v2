"""Shared helper functions for the db package."""

import json
import logging
from datetime import UTC

from .core import connect, execute

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    from datetime import datetime

    return datetime.now(UTC).isoformat()


def insert_source_run(run_record: dict) -> int | None:
    """Insert a source run record and verify the write.

    Returns the row ID on success, None on verification failure.
    """
    source_id = run_record.get("source_id", "")
    started_at = run_record.get("started_at", "")
    if len(source_id) <= 1 or len(started_at) <= 1:
        logger.warning(
            "Skipping source_run with invalid data: source_id=%r started_at=%r",
            source_id,
            started_at,
        )
        return None

    con = connect()
    try:
        cur = execute(
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
        row_id = cur.lastrowid

        # Post-write verification: confirm the row exists
        verify_cur = execute(
            con,
            "SELECT id FROM source_runs WHERE id = :row_id",
            {"row_id": row_id},
        )
        if verify_cur.fetchone() is None:
            logger.error(
                "POST_WRITE_VERIFY_FAILED",
                extra={"source_id": source_id, "run_id": row_id},
            )
            return None

        return row_id
    finally:
        con.close()
