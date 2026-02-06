import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import requests
import yaml
from jsonschema import validate

from .provenance import utc_now_iso
from .db import init_db, insert_source_run, upsert_ecfr_seen
from .notify_email import send_error_alert

ROOT = Path(__file__).resolve().parents[1]

TITLES = {
    "38": {
        "doc_id": "ECFR-title38.xml",
        "url": "https://www.govinfo.gov/bulkdata/ECFR/title-38/ECFR-title38.xml",
        "name": "Veterans' Benefits",
        "source_id": "govinfo_ecfr_title_38",
    },
    "5": {
        "doc_id": "ECFR-title5.xml",
        "url": "https://www.govinfo.gov/bulkdata/ECFR/title-5/ECFR-title5.xml",
        "name": "Administrative Personnel",
        "source_id": "govinfo_ecfr_title_5",
    },
    "20": {
        "doc_id": "ECFR-title20.xml",
        "url": "https://www.govinfo.gov/bulkdata/ECFR/title-20/ECFR-title20.xml",
        "name": "Employees' Benefits",
        "source_id": "govinfo_ecfr_title_20",
    },
}

def load_cfg() -> Dict[str, Any]:
    return yaml.safe_load((ROOT / "config" / "approved_sources.yaml").read_text(encoding="utf-8"))

def load_run_schema() -> Dict[str, Any]:
    return json.loads((ROOT / "schemas" / "source_run.schema.json").read_text(encoding="utf-8"))

def write_run_record(run_record: Dict[str, Any], title_num: str) -> None:
    outdir = ROOT / "outputs" / "runs"
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    (outdir / f"ECFR_T{title_num}_{stamp}.json").write_text(json.dumps(run_record, indent=2), encoding="utf-8")

def run_ecfr_delta(title_num: str = "38") -> Dict[str, Any]:
    title_info = TITLES[title_num]
    cfg = load_cfg()
    source = next(s for s in cfg["approved_sources"] if s["id"] == title_info["source_id"])
    url = source["endpoints"][0]
    schema = load_run_schema()

    init_db()

    started_at = utc_now_iso()
    errors: List[str] = []
    status = "SUCCESS"
    records_fetched = 0

    changed = False
    last_modified = ""
    etag = ""

    try:
        # HEAD is enough to detect changes without downloading the XML.
        r = requests.head(url, timeout=20)
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP_{r.status_code}")

        last_modified = r.headers.get("Last-Modified", "")
        etag = r.headers.get("ETag", "")
        records_fetched = 1

        changed = upsert_ecfr_seen(
            title_info["doc_id"],
            last_modified,
            etag,
            utc_now_iso(),
            url,
        )

    except Exception as e:
        status = "ERROR"
        errors.append(f"EXCEPTION: {repr(e)}")

    ended_at = utc_now_iso()

    final_status = status
    if status == "SUCCESS":
        final_status = "SUCCESS" if changed else "NO_DATA"

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
    write_run_record(run_record, title_num)

    # Send error email if needed
    if final_status == "ERROR" and errors:
        send_error_alert(source["id"], errors, run_record)

    print(json.dumps({"run_record": run_record, "changed": changed, "last_modified": last_modified, "etag": etag}, indent=2))
    return run_record

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run eCFR delta check for one or all CFR titles")
    parser.add_argument("--title", choices=list(TITLES.keys()), default="38",
                        help="CFR title number to check (default: 38)")
    parser.add_argument("--all", action="store_true", dest="all_titles",
                        help="Run delta check for all configured titles")
    return parser

if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()

    if args.all_titles:
        for t in TITLES:
            print(f"--- eCFR delta: Title {t} ({TITLES[t]['name']}) ---")
            run_ecfr_delta(t)
    else:
        run_ecfr_delta(args.title)
