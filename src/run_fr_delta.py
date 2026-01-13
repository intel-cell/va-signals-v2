import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import yaml
from jsonschema import validate

from .provenance import utc_now_iso
from .db import init_db, insert_source_run, upsert_fr_seen
from .fr_bulk import fetch_fr_listing, parse_listing_for_dates, build_date_url, fetch_fr_date_index, parse_date_index_for_packages

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

def run_fr_delta(max_days: int = 1) -> Dict[str, Any]:
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
        html = fetch_fr_listing(endpoint)
        dates = parse_listing_for_dates(html)
        if not dates:
            status = "NO_DATA"
        else:
            for ymd in dates[:max_days]:
                date_url = build_date_url(endpoint, ymd)
                idx_html = fetch_fr_date_index(date_url)
                pkgs = parse_date_index_for_packages(idx_html)
                published_date = ymd.strip("/").replace("/", "-")
                for doc_id in pkgs:
                    records_fetched += 1
                    first_seen_at = utc_now_iso()
                    source_url = date_url
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

    run_record = {
        "source_id": source["id"],
        "started_at": started_at,
        "ended_at": ended_at,
        "status": status if status != "SUCCESS" else ("NO_DATA" if len(new_docs) == 0 else "SUCCESS"),
        "records_fetched": records_fetched,
        "errors": errors,
    }

    validate(instance=run_record, schema=schema)
    insert_source_run(run_record)
    write_run_record(run_record)

    outdir = ROOT / "outputs" / "runs"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "FR_DELTA_LATEST.json").write_text(json.dumps({
        "retrieved_at": utc_now_iso(),
        "new_docs": new_docs
    }, indent=2), encoding="utf-8")

    print(json.dumps({"run_record": run_record, "new_docs_count": len(new_docs)}, indent=2))
    return run_record

if __name__ == "__main__":
    run_fr_delta()
