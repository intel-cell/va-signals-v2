"""
Log Cleanup Script

Deletes audit logs older than the retention period.
Default: 90 days (configurable via LOG_RETENTION_DAYS env var)

Run with: python -m scripts.cleanup_logs [--retention-days N] [--dry-run]
"""

import argparse
import logging
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.auth.audit import run_all_log_cleanup, get_retention_days

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Cleanup old audit logs")
    parser.add_argument(
        "--retention-days",
        type=int,
        default=None,
        help=f"Days to retain logs (default: {get_retention_days()} from env/default)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting",
    )
    args = parser.parse_args()

    retention = args.retention_days or get_retention_days()
    logger.info(f"Starting log cleanup (retention={retention} days, dry_run={args.dry_run})")

    results = run_all_log_cleanup(
        retention_days=args.retention_days,
        dry_run=args.dry_run,
    )

    if args.dry_run:
        logger.info(f"[DRY RUN] Would delete {results['total_would_delete']} total log entries")
        logger.info(f"  - audit_log: {results['audit_log']['would_delete']} entries")
        logger.info(f"  - signal_audit_log: {results['signal_audit_log']['would_delete']} entries")
    else:
        logger.info(f"Deleted {results['total_deleted']} total log entries")
        logger.info(f"  - audit_log: {results['audit_log']['deleted']} entries")
        logger.info(f"  - signal_audit_log: {results['signal_audit_log']['deleted']} entries")

    return 0


if __name__ == "__main__":
    sys.exit(main())
