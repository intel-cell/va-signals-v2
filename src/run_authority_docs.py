"""
Authority Documents Runner.

Aggregates documents from all authority sources:
- White House (statements, executive orders, memoranda)
- OMB Guidance (memoranda, circulars)
- OMB Internal Drops (manually uploaded apportionments)
- VA Publications (directives, handbooks)
- RegInfo PRA (information collection requests)

Usage:
    python -m src.run_authority_docs [--all] [--source SOURCE]
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import yaml
from jsonschema import validate

# Allow running as a script (python src/run_authority_docs.py) by setting package context
if __name__ == "__main__" and __package__ is None:
    import sys

    sys.path.append(str(Path(__file__).resolve().parent.parent))
    __package__ = "src"

from .notify_email import send_new_docs_alert, send_error_alert
from .provenance import utc_now_iso
from .db import init_db, insert_source_run, upsert_authority_doc

# Import all ingestors
from .fetch_whitehouse import fetch_whitehouse_docs
from .fetch_omb_guidance import fetch_omb_guidance_docs
from .fetch_omb_internal_drop import scan_omb_drop_folder
from .fetch_va_pubs import fetch_va_pubs_docs
from .fetch_reginfo_pra import fetch_va_pra_submissions

ROOT = Path(__file__).resolve().parents[1]

# Registry of all authority sources
AUTHORITY_SOURCES = {
    "whitehouse": {
        "name": "White House",
        "fetch_fn": fetch_whitehouse_docs,
        "default_args": {"fetch_body": True, "va_filter": False, "max_per_source": 20},
    },
    "omb": {
        "name": "OMB Guidance",
        "fetch_fn": fetch_omb_guidance_docs,
        "default_args": {"va_filter": False, "max_items": 30},
    },
    "omb_internal": {
        "name": "OMB Internal Drops",
        "fetch_fn": scan_omb_drop_folder,
        "default_args": {},
    },
    "va": {
        "name": "VA Publications",
        "fetch_fn": fetch_va_pubs_docs,
        "default_args": {"max_items": 30},
    },
    "omb_oira": {
        "name": "RegInfo PRA",
        "fetch_fn": fetch_va_pra_submissions,
        "default_args": {"max_items": 30},
    },
}


def load_run_schema() -> Dict[str, Any]:
    """Load the source run JSON schema."""
    schema_path = ROOT / "schemas" / "source_run.schema.json"
    if schema_path.exists():
        return json.loads(schema_path.read_text(encoding="utf-8"))
    # Fallback minimal schema
    return {
        "type": "object",
        "properties": {
            "source_id": {"type": "string"},
            "started_at": {"type": "string"},
            "ended_at": {"type": "string"},
            "status": {"type": "string"},
            "records_fetched": {"type": "integer"},
            "errors": {"type": "array"},
        },
    }


def write_run_record(run_record: Dict[str, Any], source_id: str) -> None:
    """Write run record to output file."""
    outdir = ROOT / "outputs" / "runs"
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"AUTHORITY_{source_id.upper()}_{stamp}.json"
    (outdir / filename).write_text(json.dumps(run_record, indent=2), encoding="utf-8")


def run_source(source_id: str) -> Dict[str, Any]:
    """
    Run a single authority source.

    Returns run record dict.
    """
    if source_id not in AUTHORITY_SOURCES:
        raise ValueError(f"Unknown source: {source_id}")

    source = AUTHORITY_SOURCES[source_id]
    fetch_fn = source["fetch_fn"]
    default_args = source["default_args"]

    started_at = utc_now_iso()
    errors: List[str] = []
    status = "SUCCESS"
    new_docs: List[Dict[str, str]] = []
    records_fetched = 0

    try:
        # Fetch documents from source
        docs = fetch_fn(**default_args)
        records_fetched = len(docs)

        if not docs:
            status = "NO_DATA"
        else:
            # Upsert each document
            for doc in docs:
                try:
                    is_new = upsert_authority_doc(doc)
                    if is_new:
                        new_docs.append({
                            "doc_id": doc["doc_id"],
                            "title": doc["title"][:100],
                            "source_url": doc["source_url"],
                            "authority_type": doc["authority_type"],
                        })
                except Exception as e:
                    errors.append(f"Error upserting {doc.get('doc_id', 'unknown')}: {repr(e)}")

    except Exception as e:
        status = "ERROR"
        errors.append(f"EXCEPTION: {repr(e)}")

    ended_at = utc_now_iso()

    # Determine final status
    final_status = status
    if status == "SUCCESS":
        final_status = "NO_DATA" if len(new_docs) == 0 else "SUCCESS"

    run_record = {
        "source_id": f"authority_{source_id}",
        "started_at": started_at,
        "ended_at": ended_at,
        "status": final_status,
        "records_fetched": records_fetched,
        "errors": errors,
    }

    return run_record, new_docs


def run_authority_docs(sources: List[str] = None) -> Dict[str, Any]:
    """
    Run authority document collection.

    Args:
        sources: List of source IDs to run, or None for all

    Returns:
        Aggregate run record
    """
    init_db()
    schema = load_run_schema()

    if sources is None:
        sources = list(AUTHORITY_SOURCES.keys())

    started_at = utc_now_iso()
    all_errors: List[str] = []
    total_fetched = 0
    all_new_docs: List[Dict[str, str]] = []
    source_results: Dict[str, Any] = {}

    for source_id in sources:
        print(f"Running {source_id}...")

        try:
            run_record, new_docs = run_source(source_id)

            # Validate and save run record
            try:
                validate(instance=run_record, schema=schema)
            except Exception:
                pass  # Schema validation is optional

            insert_source_run(run_record)
            write_run_record(run_record, source_id)

            source_results[source_id] = {
                "status": run_record["status"],
                "fetched": run_record["records_fetched"],
                "new": len(new_docs),
            }

            total_fetched += run_record["records_fetched"]
            all_new_docs.extend(new_docs)
            all_errors.extend(run_record["errors"])

            print(f"  {source_id}: {run_record['status']} - {len(new_docs)} new docs")

        except Exception as e:
            error_msg = f"{source_id}: {repr(e)}"
            all_errors.append(error_msg)
            source_results[source_id] = {"status": "ERROR", "fetched": 0, "new": 0}
            print(f"  {source_id}: ERROR - {e}")

    ended_at = utc_now_iso()

    # Determine aggregate status
    error_count = sum(1 for r in source_results.values() if r["status"] == "ERROR")
    success_count = sum(1 for r in source_results.values() if r["status"] == "SUCCESS")

    if error_count == len(sources):
        final_status = "ERROR"
    elif success_count == 0:
        final_status = "NO_DATA"
    else:
        final_status = "SUCCESS"

    aggregate_record = {
        "source_id": "authority_aggregate",
        "started_at": started_at,
        "ended_at": ended_at,
        "status": final_status,
        "records_fetched": total_fetched,
        "errors": all_errors,
    }

    # Save aggregate record
    insert_source_run(aggregate_record)
    write_run_record(aggregate_record, "aggregate")

    # Write latest new docs
    outdir = ROOT / "outputs" / "runs"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "AUTHORITY_LATEST.json").write_text(
        json.dumps({
            "retrieved_at": utc_now_iso(),
            "new_docs": all_new_docs,
            "source_results": source_results,
        }, indent=2),
        encoding="utf-8",
    )

    # Print summary
    print(f"\n=== Authority Docs Summary ===")
    print(f"Status: {final_status}")
    print(f"Total fetched: {total_fetched}")
    print(f"New documents: {len(all_new_docs)}")
    if all_errors:
        print(f"Errors: {len(all_errors)}")

    # Send email notifications
    if final_status == "ERROR" and all_errors:
        send_error_alert("authority_docs", all_errors, aggregate_record)
    elif all_new_docs:
        # Format new docs for email
        email_docs = [
            {
                "doc_id": d["doc_id"],
                "title": d["title"],
                "source_url": d["source_url"],
                "authority_type": d["authority_type"],
            }
            for d in all_new_docs[:20]  # Limit email length
        ]
        send_new_docs_alert("authority_docs", email_docs, aggregate_record)

    return aggregate_record


def main():
    parser = argparse.ArgumentParser(description="Run Authority Documents collection")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all authority sources",
    )
    parser.add_argument(
        "--source",
        type=str,
        choices=list(AUTHORITY_SOURCES.keys()),
        help="Run a specific source only",
    )
    parser.add_argument(
        "--list-sources",
        action="store_true",
        help="List available sources and exit",
    )

    args = parser.parse_args()

    if args.list_sources:
        print("Available authority sources:")
        for source_id, source in AUTHORITY_SOURCES.items():
            print(f"  {source_id}: {source['name']}")
        return

    if args.source:
        sources = [args.source]
    elif args.all:
        sources = None  # All sources
    else:
        # Default: run all
        sources = None

    result = run_authority_docs(sources)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
