import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
import yaml
from jsonschema import validate

from .provenance import utc_now_iso
from .resilience.circuit_breaker import federal_register_cb
from .resilience.retry import retry_api_call
from .resilience.wiring import circuit_breaker_sync, with_timeout

ROOT = Path(__file__).resolve().parents[1]


def run_fr_ping() -> dict[str, Any]:
    cfg = yaml.safe_load((ROOT / "config" / "approved_sources.yaml").read_text(encoding="utf-8"))
    source = next(s for s in cfg["approved_sources"] if s["id"] == "govinfo_fr_bulk")
    endpoint = source["endpoints"][0]

    started_at = utc_now_iso()
    ended_at = started_at
    errors: list[str] = []
    status = "NO_DATA"
    records_fetched = 0

    @retry_api_call
    @with_timeout(45, name="federal_register")
    @circuit_breaker_sync(federal_register_cb)
    def _ping_fr(url):
        return requests.head(url, timeout=15)

    try:
        r = _ping_fr(endpoint)
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
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    outpath = outdir / f"FR_PING_{stamp}.json"
    outpath.write_text(json.dumps(run_record, indent=2), encoding="utf-8")

    print(json.dumps(run_record, indent=2))
    return run_record


if __name__ == "__main__":
    run_fr_ping()
