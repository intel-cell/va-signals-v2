"""
Trend Aggregation Runner

Computes and stores historical aggregations for trend analysis.
Designed to run as a nightly job after pipeline completion.

Run with: python -m scripts.run_trend_aggregation [--date YYYY-MM-DD] [--backfill N]
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.trends.aggregator import run_all_aggregations

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Run trend aggregations")
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Target date (YYYY-MM-DD, default: yesterday)",
    )
    parser.add_argument(
        "--backfill",
        type=int,
        default=0,
        help="Number of days to backfill (runs aggregation for each day)",
    )
    args = parser.parse_args()

    if args.backfill > 0:
        logger.info(f"Backfilling trend aggregations for {args.backfill} days")

        for i in range(args.backfill, 0, -1):
            target_date = (datetime.now(timezone.utc) - timedelta(days=i)).date().isoformat()
            logger.info(f"Processing {target_date}...")
            try:
                results = run_all_aggregations(target_date)
                logger.info(f"  Completed: {results}")
            except Exception as e:
                logger.error(f"  Error: {e}")

        logger.info("Backfill complete")
    else:
        logger.info(f"Running trend aggregations for {args.date or 'yesterday'}")
        results = run_all_aggregations(args.date)
        logger.info(f"Results: {results}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
