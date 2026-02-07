"""
Backfill theme classifications for om_events that are missing them.

This script queries om_events with NULL theme and runs each through
the keyword-based theme extraction.

Run with: python -m scripts.backfill_om_themes [--limit N] [--dry-run]
"""

import argparse
import logging
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import connect, execute
from src.oversight.runner import _extract_theme

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def get_events_missing_theme(limit: int = 100) -> list[dict]:
    """Get om_events that don't have theme populated."""
    con = connect()
    cur = execute(
        con,
        """
        SELECT event_id, title, primary_source_type
        FROM om_events
        WHERE theme IS NULL
        ORDER BY fetched_at DESC
        LIMIT :limit
        """,
        {"limit": limit},
    )

    columns = [desc[0] for desc in cur.description]
    rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    con.close()

    return rows


def backfill_themes(limit: int = 100, dry_run: bool = False) -> dict:
    """
    Backfill theme for om_events.

    Args:
        limit: Maximum number of events to process
        dry_run: If True, don't actually update the database

    Returns:
        Stats dict with counts
    """
    stats = {"processed": 0, "updated": 0, "skipped_no_theme": 0, "errors": 0}

    events = get_events_missing_theme(limit)
    logger.info(f"Found {len(events)} om_events missing theme")

    if not events:
        return stats

    for event in events:
        stats["processed"] += 1
        try:
            title = event["title"] or ""
            source_type = event["primary_source_type"] or ""
            theme = _extract_theme(title, source_type)

            if theme is None:
                stats["skipped_no_theme"] += 1
                continue

            if dry_run:
                logger.info(
                    f"[DRY RUN] Would update {event['event_id']}: theme={theme}"
                )
            else:
                con = connect()
                execute(
                    con,
                    """
                    UPDATE om_events
                    SET theme = :theme
                    WHERE event_id = :event_id
                    """,
                    {
                        "theme": theme,
                        "event_id": event["event_id"],
                    },
                )
                con.commit()
                con.close()
                logger.info(f"Updated {event['event_id']}: theme={theme}")

            stats["updated"] += 1

        except Exception as e:
            logger.error(f"Error processing {event['event_id']}: {e}")
            stats["errors"] += 1

    return stats


def main():
    parser = argparse.ArgumentParser(description="Backfill themes for om_events")
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

    logger.info(f"Starting theme backfill (limit={args.limit}, dry_run={args.dry_run})")

    stats = backfill_themes(limit=args.limit, dry_run=args.dry_run)

    logger.info(f"Backfill complete: {stats}")
    return 0 if stats["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
