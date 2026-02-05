"""
Backfill FR document dates from Federal Register API.

This script fetches comments_close_date and effective_date for existing
FR documents in the database that are missing these fields.

Run with: python -m scripts.backfill_fr_dates [--limit N] [--dry-run]
"""

import argparse
import logging
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import connect, execute, update_fr_seen_dates
from src.fr_details import fetch_fr_documents_by_date, extract_document_dates

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def get_fr_docs_missing_dates(limit: int = 100) -> list[dict]:
    """Get FR documents that don't have date fields populated."""
    con = connect()
    cur = execute(
        con,
        """
        SELECT doc_id, published_date, source_url
        FROM fr_seen
        WHERE (comments_close_date IS NULL OR comments_close_date = '')
          AND (effective_date IS NULL OR effective_date = '')
        ORDER BY published_date DESC
        LIMIT :limit
        """,
        {"limit": limit},
    )

    columns = [desc[0] for desc in cur.description]
    rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    con.close()

    return rows


def backfill_dates(limit: int = 100, dry_run: bool = False) -> dict:
    """
    Backfill date fields for FR documents.

    Args:
        limit: Maximum number of documents to process
        dry_run: If True, don't actually update the database

    Returns:
        Stats dict with counts
    """
    stats = {"processed": 0, "updated": 0, "skipped_no_data": 0, "errors": 0}

    docs = get_fr_docs_missing_dates(limit)
    logger.info(f"Found {len(docs)} FR documents missing date fields")

    if not docs:
        return stats

    # Group by publication date to minimize API calls
    dates_to_docs: dict[str, list[str]] = {}
    for doc in docs:
        pub_date = doc["published_date"]
        if pub_date:
            if pub_date not in dates_to_docs:
                dates_to_docs[pub_date] = []
            dates_to_docs[pub_date].append(doc["doc_id"])

    logger.info(f"Processing {len(dates_to_docs)} unique publication dates")

    for pub_date, doc_ids in dates_to_docs.items():
        logger.info(f"Fetching FR documents for {pub_date}...")

        try:
            # Fetch VA-related documents for this date
            fr_docs = fetch_fr_documents_by_date(
                pub_date,
                agencies=["veterans-affairs-department"],
            )

            if not fr_docs:
                logger.warning(f"No VA documents found for {pub_date}")
                stats["skipped_no_data"] += len(doc_ids)
                continue

            # Process each document
            for fr_doc in fr_docs:
                stats["processed"] += 1
                dates = extract_document_dates(fr_doc)

                # Only update if we have at least one date
                if dates["comments_close_date"] or dates["effective_date"]:
                    doc_num = fr_doc.get("document_number", "")

                    if dry_run:
                        logger.info(
                            f"[DRY RUN] Would update {doc_num}: "
                            f"comments_close={dates['comments_close_date']}, "
                            f"effective={dates['effective_date']}"
                        )
                    else:
                        # Find matching doc_id (FR-YYYY-MM-DD format)
                        for doc_id in doc_ids:
                            update_fr_seen_dates(
                                doc_id=doc_id,
                                comments_close_date=dates["comments_close_date"],
                                effective_date=dates["effective_date"],
                                document_type=dates["document_type"],
                                title=dates["title"],
                            )
                            logger.info(f"Updated {doc_id} with dates from {doc_num}")
                            stats["updated"] += 1

        except Exception as e:
            logger.error(f"Error processing {pub_date}: {e}")
            stats["errors"] += 1

    return stats


def main():
    parser = argparse.ArgumentParser(description="Backfill FR document dates")
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of documents to process (default: 100)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't actually update the database",
    )
    args = parser.parse_args()

    logger.info(f"Starting backfill (limit={args.limit}, dry_run={args.dry_run})")

    stats = backfill_dates(limit=args.limit, dry_run=args.dry_run)

    logger.info(f"Backfill complete: {stats}")
    return 0 if stats["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
