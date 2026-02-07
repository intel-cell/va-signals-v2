"""
Backfill program detection for state signals missing a program field.

Queries state_signals WHERE program IS NULL, runs detect_program() on
title + content, and updates the record.

Run with: python -m scripts.backfill_state_programs [--limit N] [--dry-run]
"""

import argparse
import logging
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import connect, execute
from src.state.common import detect_program

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def get_signals_missing_program(limit: int = 100) -> list[dict]:
    """Get state signals that don't have a program field populated."""
    con = connect()
    cur = execute(
        con,
        """
        SELECT signal_id, title, content
        FROM state_signals
        WHERE program IS NULL
        ORDER BY fetched_at DESC
        LIMIT :limit
        """,
        {"limit": limit},
    )
    columns = [desc[0] for desc in cur.description]
    rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    con.close()
    return rows


def backfill_programs(limit: int = 100, dry_run: bool = False) -> dict:
    """
    Backfill program field for state signals.

    Args:
        limit: Maximum number of signals to process
        dry_run: If True, don't actually update the database

    Returns:
        Stats dict with counts
    """
    stats = {"processed": 0, "updated": 0, "skipped_no_match": 0, "errors": 0}

    signals = get_signals_missing_program(limit)
    logger.info(f"Found {len(signals)} state signals missing program field")

    if not signals:
        return stats

    for sig in signals:
        stats["processed"] += 1
        try:
            text = f"{sig['title']} {sig['content'] or ''}"
            program = detect_program(text)

            if program is None:
                stats["skipped_no_match"] += 1
                continue

            if dry_run:
                logger.info(
                    f"[DRY RUN] Would update {sig['signal_id'][:12]}... "
                    f"program={program}"
                )
            else:
                con = connect()
                execute(
                    con,
                    "UPDATE state_signals SET program = :program WHERE signal_id = :signal_id",
                    {"program": program, "signal_id": sig["signal_id"]},
                )
                con.commit()
                con.close()
                logger.info(f"Updated {sig['signal_id'][:12]}... program={program}")

            stats["updated"] += 1

        except Exception as e:
            logger.error(f"Error processing {sig['signal_id'][:12]}...: {e}")
            stats["errors"] += 1

    return stats


def main():
    parser = argparse.ArgumentParser(description="Backfill state signal programs")
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

    stats = backfill_programs(limit=args.limit, dry_run=args.dry_run)

    logger.info(f"Backfill complete: {stats}")
    return 0 if stats["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
