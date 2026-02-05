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

DOC_ID = "ECFR-title38.xml"

def load_cfg() -> Dict[str, Any]:
    return yaml.safe_load((ROOT / "config" / "approved_sources.yaml").read_text(encoding="utf-8"))

def load_run_schema() -> Dict[str, Any]:
    return json.loads((ROOT / "schemas" / "source_run.schema.json").read_text(encoding="utf-8"))

def write_run_record(run_record: Dict[str, Any]) -> None:
    outdir = ROOT / "outputs" / "runs"
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    (outdir / f"ECFR_T38_{stamp}.json").write_text(json.dumps(run_record, indent=2), encoding="utf-8")

def run_ecfr_delta() -> Dict[str, Any]:
    cfg = load_cfg()
    source = next(s for s in cfg["approved_sources"] if s["id"] == "govinfo_ecfr_title_38")
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
            DOC_ID,
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
    write_run_record(run_record)

    # Send error email if needed
    if final_status == "ERROR" and errors:
        send_error_alert(source["id"], errors, run_record)

    print(json.dumps({"run_record": run_record, "changed": changed, "last_modified": last_modified, "etag": etag}, indent=2))
    return run_record

if __name__ == "__main__":
    run_ecfr_delta()
