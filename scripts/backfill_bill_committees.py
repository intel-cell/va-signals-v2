"""
Backfill committee data for existing bills.

Fetches committee assignments from Congress.gov API for bills that have
empty or missing committees_json.

Run with: python -m scripts.backfill_bill_committees [--limit N] [--dry-run] [--congress N]
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import connect, execute, update_committees_json
from src.fetch_bills import fetch_bill_committees, parse_bill_id

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def get_bills_missing_committees(limit: int = 100, congress: int | None = None) -> list[dict]:
    """Get bills that don't have committee data populated."""
    con = connect()
    sql = """
        SELECT bill_id, congress, bill_type, bill_number
        FROM bills
        WHERE committees_json IS NULL
           OR committees_json = '[]'
           OR committees_json = ''
    """
    params: dict = {}
    if congress is not None:
        sql += " AND congress = :congress"
        params["congress"] = congress
    sql += " ORDER BY latest_action_date DESC LIMIT :limit"
    params["limit"] = limit

    cur = execute(con, sql, params)
    columns = [desc[0] for desc in cur.description]
    rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    con.close()
    return rows


def backfill_committees(
    limit: int = 100, dry_run: bool = False, congress: int | None = None
) -> dict:
    """
    Backfill committee data for bills missing it.

    Args:
        limit: Maximum number of bills to process
        dry_run: If True, don't actually update the database
        congress: Optional congress number filter

    Returns:
        Stats dict with counts
    """
    stats = {"processed": 0, "updated": 0, "skipped_no_data": 0, "errors": 0}

    bills = get_bills_missing_committees(limit=limit, congress=congress)
    logger.info(f"Found {len(bills)} bills missing committee data")

    if not bills:
        return stats

    for bill in bills:
        bill_id = bill["bill_id"]
        stats["processed"] += 1

        try:
            congress_num, bill_type, bill_number = parse_bill_id(bill_id)
        except ValueError as e:
            logger.error(f"Cannot parse bill_id {bill_id}: {e}")
            stats["errors"] += 1
            continue

        try:
            committees = fetch_bill_committees(congress_num, bill_type, bill_number)
        except Exception as e:
            logger.error(f"Error fetching committees for {bill_id}: {e}")
            stats["errors"] += 1
            continue

        if not committees:
            logger.info(f"No committee data found for {bill_id}")
            stats["skipped_no_data"] += 1
        elif dry_run:
            logger.info(
                f"[DRY RUN] Would update {bill_id}: {len(committees)} committees"
            )
            stats["updated"] += 1
        else:
            update_committees_json(bill_id, json.dumps(committees))
            logger.info(f"Updated {bill_id} with {len(committees)} committees")
            stats["updated"] += 1

        time.sleep(0.5)

    return stats


def main():
    parser = argparse.ArgumentParser(description="Backfill bill committee data")
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of bills to process (default: 100)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't actually update the database",
    )
    parser.add_argument(
        "--congress",
        type=int,
        default=None,
        help="Filter by congress number (e.g., 119)",
    )
    args = parser.parse_args()

    logger.info(
        f"Starting backfill (limit={args.limit}, dry_run={args.dry_run}, "
        f"congress={args.congress})"
    )

    stats = backfill_committees(
        limit=args.limit, dry_run=args.dry_run, congress=args.congress
    )

    logger.info(f"Backfill complete: {stats}")
    return 0 if stats["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
