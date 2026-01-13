import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List

import requests
import yaml
from jsonschema import validate

from .provenance import utc_now_iso

ROOT = Path(__file__).resolve().parents[1]

def run_fr_ping() -> Dict[str, Any]:
    cfg = yaml.safe_load((ROOT / "config" / "approved_sources.yaml").read_text(encoding="utf-8"))
    source = next(s for s in cfg["approved_sources"] if s["id"] == "govinfo_fr_bulk")
    endpoint = source["endpoints"][0]

    started_at = utc_now_iso()
    ended_at = started_at
    errors: List[str] = []
    status = "NO_DATA"
    records_fetched = 0

    try:
        r = requests.head(endpoint, timeout=15)
        if r.status_code >= 400:
            status = "ERROR"
            errors.append(f"HTTP_{r.status_code}: {endpoint}")
    except Exception as e:
        status = "ERROR"
        errors.append(f"EXCEPTION: {repr(e)}")

    ended_at = utc_now_iso()

    run_record = {
        "source_id": source["id"],
        "started_at": started_at,
        "ended_at": ended_at,
        "status": status,
        "records_fetched": records_fetched,
        "errors": errors,
    }

    schema = json.loads((ROOT / "schemas" / "source_run.schema.json").read_text(encoding="utf-8"))
    validate(instance=run_record, schema=schema)

    outdir = ROOT / "outputs" / "runs"
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    outpath = outdir / f"FR_PING_{stamp}.json"
    outpath.write_text(json.dumps(run_record, indent=2), encoding="utf-8")

    print(json.dumps(run_record, indent=2))
    return run_record

if __name__ == "__main__":
    run_fr_ping()
