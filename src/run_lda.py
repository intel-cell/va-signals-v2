"""
CLI runner for LDA.gov Lobbying Disclosure delta detection.

Follows the run_fr_delta.py pattern: fetch → upsert → alert → log to source_runs.

Usage:
    python -m src.run_lda --mode daily              # Delta detection (default)
    python -m src.run_lda --mode daily --dry-run    # Fetch only, no DB writes
    python -m src.run_lda --mode daily --since 2026-01-01  # Custom start date
    python -m src.run_lda --summary                 # Show stats
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import yaml
from jsonschema import validate

# Allow running as a script
if __name__ == "__main__" and __package__ is None:
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    __package__ = "src"

from .db import init_db, insert_source_run, upsert_lda_filing, insert_lda_alert, get_lda_stats
from .fetch_lda import (
    fetch_filings_since,
    fetch_registrations_since,
    fetch_amendments_since,
    evaluate_alerts,
)
from .notify_email import send_new_docs_alert, send_error_alert
from .provenance import utc_now_iso

ROOT = Path(__file__).resolve().parents[1]
logger = logging.getLogger(__name__)


def load_cfg() -> Dict[str, Any]:
    return yaml.safe_load((ROOT / "config" / "approved_sources.yaml").read_text(encoding="utf-8"))


def load_run_schema() -> Dict[str, Any]:
    return json.loads((ROOT / "schemas" / "source_run.schema.json").read_text(encoding="utf-8"))


def write_run_record(run_record: Dict[str, Any]) -> None:
    outdir = ROOT / "outputs" / "runs"
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    (outdir / f"LDA_DAILY_{stamp}.json").write_text(
        json.dumps(run_record, indent=2), encoding="utf-8"
    )


def run_lda_daily(since: str = None, dry_run: bool = False) -> Dict[str, Any]:
    """
    Run LDA daily delta detection.

    Args:
        since: ISO date to fetch filings from (default: yesterday)
        dry_run: If True, fetch but don't write to DB

    Returns:
        Run record dict
    """
    cfg = load_cfg()
    source = next(s for s in cfg["approved_sources"] if s["id"] == "lda_gov")
    schema = load_run_schema()

    init_db()

    started_at = utc_now_iso()
    errors: List[str] = []
    status = "SUCCESS"
    records_fetched = 0
    new_filings: List[Dict[str, Any]] = []
    all_alerts: List[Dict[str, Any]] = []

    # Default to yesterday
    if not since:
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        since = yesterday.strftime("%Y-%m-%d")

    try:
        # Fetch all VA-targeting filings since date
        logger.info(f"LDA: Fetching filings since {since}...")
        filings = fetch_filings_since(since)
        records_fetched = len(filings)
        logger.info(f"LDA: Got {records_fetched} filings")

        if not filings:
            status = "NO_DATA"
        else:
            for filing in filings:
                if dry_run:
                    new_filings.append({
                        "filing_uuid": filing["filing_uuid"],
                        "filing_type": filing["filing_type"],
                        "registrant_name": filing["registrant_name"],
                        "client_name": filing["client_name"],
                        "va_relevance_score": filing["va_relevance_score"],
                        "source_url": filing["source_url"],
                    })
                    continue

                is_new = upsert_lda_filing(filing)
                if is_new:
                    new_filings.append({
                        "filing_uuid": filing["filing_uuid"],
                        "filing_type": filing["filing_type"],
                        "registrant_name": filing["registrant_name"],
                        "client_name": filing["client_name"],
                        "va_relevance_score": filing["va_relevance_score"],
                        "source_url": filing["source_url"],
                    })

                    # Evaluate alert conditions
                    alerts = evaluate_alerts(filing)
                    for alert in alerts:
                        alert_id = insert_lda_alert(alert)
                        alert["id"] = alert_id
                        all_alerts.append(alert)

    except Exception as e:
        status = "ERROR"
        errors.append(f"EXCEPTION: {repr(e)}")
        logger.error(f"LDA daily run failed: {e}")

    ended_at = utc_now_iso()

    final_status = status
    if status == "SUCCESS":
        final_status = "NO_DATA" if len(new_filings) == 0 else "SUCCESS"

    run_record = {
        "source_id": source["id"],
        "started_at": started_at,
        "ended_at": ended_at,
        "status": final_status,
        "records_fetched": records_fetched,
        "errors": errors,
    }

    if not dry_run:
        validate(instance=run_record, schema=schema)
        insert_source_run(run_record)
        write_run_record(run_record)

    # Write LATEST.json
    outdir = ROOT / "outputs" / "runs"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "LDA_LATEST.json").write_text(
        json.dumps({
            "retrieved_at": utc_now_iso(),
            "since": since,
            "new_filings": new_filings,
            "alerts": [
                {"alert_type": a["alert_type"], "severity": a["severity"], "summary": a["summary"]}
                for a in all_alerts
            ],
        }, indent=2),
        encoding="utf-8",
    )

    # Print summary
    print(json.dumps({"run_record": run_record, "new_filings_count": len(new_filings), "alerts_count": len(all_alerts)}, indent=2))

    # Email notifications
    if not dry_run:
        if final_status == "ERROR" and errors:
            send_error_alert(source["id"], errors, run_record)
        elif new_filings and any(a.get("severity") in ("HIGH", "CRITICAL") for a in all_alerts):
            # Format filings as docs for email
            docs = [
                {
                    "doc_id": f["filing_uuid"],
                    "published_date": f.get("dt_posted", ""),
                    "source_url": f["source_url"],
                    "retrieved_at": utc_now_iso(),
                }
                for f in new_filings
                if f.get("va_relevance_score") in ("HIGH", "CRITICAL")
            ]
            if docs:
                send_new_docs_alert(source["id"], docs, run_record)

    return run_record


def show_summary():
    """Print LDA filing statistics."""
    init_db()
    stats = get_lda_stats()

    print("\n=== LDA Lobbying Disclosure Stats ===")
    print(f"Total filings: {stats['total_filings']}")

    if stats["by_type"]:
        print("\nBy filing type:")
        for ftype, count in sorted(stats["by_type"].items()):
            print(f"  {ftype}: {count}")

    if stats["by_relevance"]:
        print("\nBy VA relevance:")
        for score, count in sorted(stats["by_relevance"].items()):
            print(f"  {score}: {count}")

    print(f"\nUnacknowledged alerts: {stats['unacknowledged_alerts']}")


def main():
    parser = argparse.ArgumentParser(description="LDA.gov Lobbying Disclosure Delta Detection")
    parser.add_argument("--mode", default="daily", choices=["daily"], help="Run mode (default: daily)")
    parser.add_argument("--since", help="Fetch filings since this date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Fetch but don't write to DB")
    parser.add_argument("--summary", action="store_true", help="Show filing stats")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.summary:
        show_summary()
        return

    if args.mode == "daily":
        run_lda_daily(since=args.since, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
