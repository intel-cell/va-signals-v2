import os
import json
import requests
from typing import Any, Dict, Optional

def post_slack(payload: Dict[str, Any], timeout: int = 10) -> None:
    url = os.environ.get("SLACK_WEBHOOK_URL")
    if not url:
        raise RuntimeError("SLACK_WEBHOOK_URL missing")

    r = requests.post(url, data=json.dumps(payload), headers={"Content-Type": "application/json"}, timeout=timeout)
    if r.status_code >= 400:
        raise RuntimeError(f"Slack webhook failed: HTTP {r.status_code} {r.text[:200]}")

def format_fr_delta_alert(run_record: Dict[str, Any], new_docs_count: int) -> Optional[Dict[str, Any]]:
    status = run_record.get("status")
    if status == "ERROR":
        return {
            "text": f"VA Signals V2 — FR Delta ERROR\nsource={run_record.get('source_id')} records={run_record.get('records_fetched')} errors={run_record.get('errors')}"
        }
    if new_docs_count > 0:
        return {
            "text": f"VA Signals V2 — FR Delta NEW DOCS: {new_docs_count}\nsource={run_record.get('source_id')} records_scanned={run_record.get('records_fetched')}"
        }
    return None
