"""
Backfill ML scores for om_events that are missing them.

This script queries om_events with NULL ml_score and runs each through
the ML scoring pipeline.

Run with: python -m scripts.backfill_om_ml_scores [--limit N] [--dry-run]
"""

import argparse
import logging
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import connect, execute
from src.oversight.pipeline.escalation import _try_ml_score

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def get_events_missing_ml_score(limit: int = 100) -> list[dict]:
    """Get om_events that don't have ml_score populated."""
    con = connect()
    cur = execute(
        con,
        """
        SELECT event_id, title, raw_content
        FROM om_events
        WHERE ml_score IS NULL
        ORDER BY fetched_at DESC
        LIMIT :limit
        """,
        {"limit": limit},
    )

    columns = [desc[0] for desc in cur.description]
    rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    con.close()

    return rows


def backfill_ml_scores(limit: int = 100, dry_run: bool = False) -> dict:
    """
    Backfill ml_score and ml_risk_level for om_events.

    Args:
        limit: Maximum number of events to process
        dry_run: If True, don't actually update the database

    Returns:
        Stats dict with counts
    """
    stats = {"processed": 0, "updated": 0, "skipped_no_score": 0, "errors": 0}

    events = get_events_missing_ml_score(limit)
    logger.info(f"Found {len(events)} om_events missing ml_score")

    if not events:
        return stats

    for event in events:
        stats["processed"] += 1
        try:
            title = event["title"] or ""
            content = event["raw_content"] or ""
            ml_score, ml_risk_level, _ = _try_ml_score(title, content)

            if ml_score is None:
                stats["skipped_no_score"] += 1
                continue

            if dry_run:
                logger.info(
                    f"[DRY RUN] Would update {event['event_id']}: "
                    f"ml_score={ml_score}, ml_risk_level={ml_risk_level}"
                )
            else:
                con = connect()
                execute(
                    con,
                    """
                    UPDATE om_events
                    SET ml_score = :ml_score, ml_risk_level = :ml_risk_level
                    WHERE event_id = :event_id
                    """,
                    {
                        "ml_score": ml_score,
                        "ml_risk_level": ml_risk_level,
                        "event_id": event["event_id"],
                    },
                )
                con.commit()
                con.close()
                logger.info(f"Updated {event['event_id']}: ml_score={ml_score}")

            stats["updated"] += 1

        except Exception as e:
            logger.error(f"Error processing {event['event_id']}: {e}")
            stats["errors"] += 1

    return stats


def main():
    parser = argparse.ArgumentParser(description="Backfill ML scores for om_events")
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of events to process (default: 100)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't actually update the database",
    )
    args = parser.parse_args()

    logger.info(f"Starting ML score backfill (limit={args.limit}, dry_run={args.dry_run})")

    stats = backfill_ml_scores(limit=args.limit, dry_run=args.dry_run)

    logger.info(f"Backfill complete: {stats}")
    return 0 if stats["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
