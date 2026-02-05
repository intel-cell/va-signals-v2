import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import yaml
from jsonschema import validate

# Allow running as a script (python src/run_fr_delta.py) by setting package context
if __name__ == "__main__" and __package__ is None:
    import sys

    sys.path.append(str(Path(__file__).resolve().parent.parent))
    __package__ = "src"

from .notify_email import send_new_docs_alert, send_error_alert
from .provenance import utc_now_iso
from .db import init_db, insert_source_run, upsert_fr_seen
from .fr_bulk import list_latest_month_folders, list_month_packages

ROOT = Path(__file__).resolve().parents[1]


def load_cfg() -> Dict[str, Any]:
    return yaml.safe_load((ROOT / "config" / "approved_sources.yaml").read_text(encoding="utf-8"))


def load_run_schema() -> Dict[str, Any]:
    return json.loads((ROOT / "schemas" / "source_run.schema.json").read_text(encoding="utf-8"))


def write_run_record(run_record: Dict[str, Any]) -> None:
    outdir = ROOT / "outputs" / "runs"
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    (outdir / f"FR_DELTA_{stamp}.json").write_text(json.dumps(run_record, indent=2), encoding="utf-8")


def run_fr_delta(max_months: int = 3) -> Dict[str, Any]:
    cfg = load_cfg()
    source = next(s for s in cfg["approved_sources"] if s["id"] == "govinfo_fr_bulk")
    endpoint = source["endpoints"][0]
    schema = load_run_schema()

    init_db()

    started_at = utc_now_iso()
    errors: List[str] = []
    status = "SUCCESS"
    records_fetched = 0
    new_docs: List[Dict[str, str]] = []

    try:
        month_folders = list_latest_month_folders(endpoint, max_months=max_months)
        if not month_folders:
            status = "NO_DATA"
        else:
            for _, month_url in month_folders:
                for pkg in list_month_packages(month_url):
                    doc_id = pkg["doc_id"]
                    published_date = pkg["published_date"]
                    records_fetched += 1
                    first_seen_at = utc_now_iso()
                    source_url = pkg["source_url"]
                    if upsert_fr_seen(doc_id, published_date, first_seen_at, source_url):
                        new_docs.append({
                            "doc_id": doc_id,
                            "published_date": published_date,
                            "source_url": source_url,
                            "retrieved_at": first_seen_at
                        })
    except Exception as e:
        status = "ERROR"
        errors.append(f"EXCEPTION: {repr(e)}")

    ended_at = utc_now_iso()

    final_status = status
    if status == "SUCCESS":
        final_status = "NO_DATA" if len(new_docs) == 0 else "SUCCESS"

    run_record = {
        "source_id": source["id"],
        "started_at": started_at,
        "ended_at": ended_at,
        "status": final_status,
        "records_fetched": records_fetched,
        "errors": errors,
    }

    validate(instance=run_record, schema=schema)
    insert_source_run(run_record)
    write_run_record(run_record)

    outdir = ROOT / "outputs" / "runs"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "FR_DELTA_LATEST.json").write_text(
        json.dumps({"retrieved_at": utc_now_iso(), "new_docs": new_docs}, indent=2),
        encoding="utf-8",
    )

    new_docs_count = len(new_docs)
    print(json.dumps({"run_record": run_record, "new_docs_count": new_docs_count}, indent=2))

    # Send email notifications
    if final_status == "ERROR" and errors:
        send_error_alert(source["id"], errors, run_record)
    elif new_docs:
        send_new_docs_alert(source["id"], new_docs, run_record)

    return run_record


if __name__ == "__main__":
    run_fr_delta()
