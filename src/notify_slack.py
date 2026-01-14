import os
import requests
from typing import Any, Dict, Optional

def post_slack(payload: Dict[str, Any], timeout: int = 5) -> None:
    token = os.environ.get("SLACK_BOT_TOKEN")
    channel = os.environ.get("SLACK_CHANNEL")

    if not token:
        raise RuntimeError("SLACK_BOT_TOKEN missing")
    if not channel:
        raise RuntimeError("SLACK_CHANNEL missing")

    r = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "channel": channel,
            **payload,
        },
        timeout=timeout,
    )

    data = r.json() if r.content else {}
    if (not r.ok) or (not data.get("ok")):
        raise RuntimeError(f"Slack API error: {data}")

def format_fr_delta_alert(run_record: Dict[str, Any], new_docs: list[dict]) -> Optional[Dict[str, Any]]:
    status = run_record.get("status")

    if status == "ERROR":
        return {
            "text": (
                "VA Signals — FR Delta ERROR\n"
                f"source={run_record.get('source_id')} "
                f"records={run_record.get('records_fetched')} "
                f"errors={run_record.get('errors')}"
            )
        }

    if len(new_docs) > 0:
        lines = []
        for d in new_docs[:10]:
            doc_id = d.get("doc_id", "")
            url = d.get("source_url", "")
            if doc_id and url:
                lines.append(f"- {doc_id} — {url}")
            elif doc_id:
                lines.append(f"- {doc_id}")

        more = f"\n(+{len(new_docs) - 10} more)" if len(new_docs) > 10 else ""

        return {
            "text": (
                f"VA Signals — FR Delta NEW DOCS: {len(new_docs)}\n"
                f"source={run_record.get('source_id')} records_scanned={run_record.get('records_fetched')}\n\n"
                + "\n".join(lines)
                + more
            )
        }

    return None
