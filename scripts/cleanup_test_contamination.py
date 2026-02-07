#!/usr/bin/env python3
"""
Clean up test contamination from the database.

Removes rows that should never exist in production:
- audit_log entries from test clients
- hearings with far-future placeholder dates
- source_runs with stub identifiers

Run with: python -m scripts.cleanup_test_contamination [--dry-run] [--limit N]
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import connect, execute

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def count_contaminated(con) -> dict:
    """Count contaminated rows in each table."""
    counts = {}

    cur = execute(con, "SELECT COUNT(*) FROM audit_log WHERE ip_address = 'testclient'")
    counts["audit_log_testclient"] = cur.fetchone()[0]

    cur = execute(con, "SELECT COUNT(*) FROM hearings WHERE substr(hearing_date, 1, 4) >= '2099'")
    counts["hearings_placeholder_dates"] = cur.fetchone()[0]

    cur = execute(
        con,
        "SELECT COUNT(*) FROM source_runs WHERE length(source_id) <= 1 OR length(started_at) <= 1",
    )
    counts["source_runs_stub"] = cur.fetchone()[0]

    return counts


def run_cleanup(dry_run: bool = False, limit: int = 0) -> dict:
    """
    Remove contaminated rows from the database.

    Args:
        dry_run: If True, count but don't delete.
        limit: Max rows to delete per table (0 = unlimited).

    Returns:
        Stats dict with counts.
    """
    stats = {"scanned": 0, "deleted": 0, "tables": {}}

    con = connect()

    counts = count_contaminated(con)
    stats["scanned"] = sum(counts.values())

    logger.info("Contaminated rows found: %s", counts)

    if dry_run:
        logger.info("[DRY RUN] No rows will be deleted.")
        stats["tables"] = counts
        con.close()
        return stats

    limit_clause = f" LIMIT {limit}" if limit > 0 else ""

    # audit_log
    if counts["audit_log_testclient"] > 0:
        if limit > 0:
            execute(
                con,
                f"DELETE FROM audit_log WHERE rowid IN "
                f"(SELECT rowid FROM audit_log WHERE ip_address = 'testclient'{limit_clause})",
            )
        else:
            execute(con, "DELETE FROM audit_log WHERE ip_address = 'testclient'")
        deleted = counts["audit_log_testclient"] if limit == 0 else min(limit, counts["audit_log_testclient"])
        stats["tables"]["audit_log_testclient"] = deleted
        stats["deleted"] += deleted

    # hearings
    if counts["hearings_placeholder_dates"] > 0:
        if limit > 0:
            execute(
                con,
                f"DELETE FROM hearings WHERE rowid IN "
                f"(SELECT rowid FROM hearings WHERE substr(hearing_date, 1, 4) >= '2099'{limit_clause})",
            )
        else:
            execute(con, "DELETE FROM hearings WHERE substr(hearing_date, 1, 4) >= '2099'")
        deleted = counts["hearings_placeholder_dates"] if limit == 0 else min(limit, counts["hearings_placeholder_dates"])
        stats["tables"]["hearings_placeholder_dates"] = deleted
        stats["deleted"] += deleted

    # source_runs
    if counts["source_runs_stub"] > 0:
        if limit > 0:
            execute(
                con,
                f"DELETE FROM source_runs WHERE rowid IN "
                f"(SELECT rowid FROM source_runs WHERE length(source_id) <= 1 OR length(started_at) <= 1{limit_clause})",
            )
        else:
            execute(
                con,
                "DELETE FROM source_runs WHERE length(source_id) <= 1 OR length(started_at) <= 1",
            )
        deleted = counts["source_runs_stub"] if limit == 0 else min(limit, counts["source_runs_stub"])
        stats["tables"]["source_runs_stub"] = deleted
        stats["deleted"] += deleted

    con.commit()
    con.close()

    return stats


def main():
    parser = argparse.ArgumentParser(description="Clean up test contamination from database")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count contaminated rows without deleting",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximum rows to delete per table (default: 0 = unlimited)",
    )
    args = parser.parse_args()

    logger.info("Starting cleanup (dry_run=%s, limit=%s)", args.dry_run, args.limit)

    stats = run_cleanup(dry_run=args.dry_run, limit=args.limit)

    logger.info("Cleanup complete: %s", stats)
    print(f"\nSummary: scanned={stats['scanned']}, deleted={stats['deleted']}")
    for table, count in stats.get("tables", {}).items():
        print(f"  {table}: {count}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
