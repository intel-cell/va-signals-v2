"""
Backfill notification records for state signals that have no notification entry.

Queries state_signals joined with state_classifications that have no
corresponding state_notifications record, and inserts digest_queued entries.

Run with: python -m scripts.backfill_state_notifications [--limit N] [--dry-run]
"""

import argparse
import logging
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import connect, execute
from src.state.db_helpers import mark_signal_notified

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def get_signals_missing_notifications(limit: int = 100) -> list[dict]:
    """Get classified state signals that have no notification record."""
    con = connect()
    cur = execute(
        con,
        """
        SELECT s.signal_id, c.severity
        FROM state_signals s
        JOIN state_classifications c ON s.signal_id = c.signal_id
        LEFT JOIN state_notifications n ON s.signal_id = n.signal_id
        WHERE n.signal_id IS NULL
        ORDER BY c.classified_at DESC
        LIMIT :limit
        """,
        {"limit": limit},
    )
    columns = [desc[0] for desc in cur.description]
    rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    con.close()
    return rows


def backfill_notifications(limit: int = 100, dry_run: bool = False) -> dict:
    """
    Backfill notification records for signals missing them.

    Args:
        limit: Maximum number of signals to process
        dry_run: If True, don't actually update the database

    Returns:
        Stats dict with counts
    """
    stats = {"processed": 0, "updated": 0, "errors": 0}

    signals = get_signals_missing_notifications(limit)
    logger.info(f"Found {len(signals)} signals missing notification records")

    if not signals:
        return stats

    for sig in signals:
        stats["processed"] += 1
        try:
            if dry_run:
                logger.info(
                    f"[DRY RUN] Would insert notification for "
                    f"{sig['signal_id'][:12]}... severity={sig['severity']} "
                    f"method=digest_queued"
                )
            else:
                mark_signal_notified(sig["signal_id"], "digest_queued")
                logger.info(
                    f"Inserted notification for {sig['signal_id'][:12]}... "
                    f"severity={sig['severity']} method=digest_queued"
                )

            stats["updated"] += 1

        except Exception as e:
            logger.error(f"Error processing {sig['signal_id'][:12]}...: {e}")
            stats["errors"] += 1

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Backfill state signal notification records"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of signals to process (default: 100)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't actually update the database",
    )
    args = parser.parse_args()

    logger.info(f"Starting backfill (limit={args.limit}, dry_run={args.dry_run})")

    stats = backfill_notifications(limit=args.limit, dry_run=args.dry_run)

    logger.info(f"Backfill complete: {stats}")
    return 0 if stats["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
