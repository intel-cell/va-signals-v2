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


def format_agenda_drift_alert(events: list[dict]) -> Optional[Dict[str, Any]]:
    """
    Format agenda drift deviation events for Slack.
    Returns None if no events, else {"text": "..."}.
    """
    if not events:
        return None

    lines = [f"VA Signals — Agenda Drift: {len(events)} deviation(s)"]
    for e in events[:5]:
        member = e.get("member_name", e.get("member_id", "Unknown"))
        z = e.get("zscore", 0)
        hearing = e.get("hearing_id", "")
        note = e.get("note", "")
        line = f"- {member}: z={z:.1f}"
        if hearing:
            line += f" ({hearing})"
        if note:
            line += f" — {note}"
        lines.append(line)

    if len(events) > 5:
        lines.append(f"(+{len(events) - 5} more)")

    return {"text": "\n".join(lines)}


def format_new_bills_alert(bills: list[dict]) -> Optional[Dict[str, Any]]:
    """
    Format new bills alert for Slack.

    Format: "VA Signals — N new bill(s) introduced"
    List each bill: HR 1234: Title (Rep. Name, R-ST)

    Args:
        bills: List of bill dicts with keys:
            bill_type, bill_number, title, sponsor_name, sponsor_party, sponsor_state

    Returns:
        Slack payload dict or None if no bills
    """
    if not bills:
        return None

    count = len(bills)
    plural = "s" if count != 1 else ""
    lines = [f"VA Signals — {count} new bill{plural} introduced"]

    for bill in bills[:10]:
        bill_ref = f"{bill.get('bill_type', '')} {bill.get('bill_number', '')}"
        title = bill.get("title", "")
        if len(title) > 60:
            title = title[:57] + "..."

        sponsor_name = bill.get("sponsor_name", "")
        sponsor_party = bill.get("sponsor_party", "")
        sponsor_state = bill.get("sponsor_state", "")

        line = f"- {bill_ref}: {title}"
        if sponsor_name:
            sponsor_info = sponsor_name
            if sponsor_party and sponsor_state:
                sponsor_info += f", {sponsor_party}-{sponsor_state}"
            line += f" ({sponsor_info})"

        lines.append(line)

    if count > 10:
        lines.append(f"(+{count - 10} more)")

    return {"text": "\n".join(lines)}


def format_bill_status_alert(actions: list[dict]) -> Optional[Dict[str, Any]]:
    """
    Format bill status update alert for Slack.

    Format: "VA Signals — Bill status updates"
    List each: HR 1234: Action text

    Args:
        actions: List of action dicts with keys:
            bill_id, bill_type, bill_number, title, action_date, action_text

    Returns:
        Slack payload dict or None if no actions
    """
    if not actions:
        return None

    count = len(actions)
    plural = "s" if count != 1 else ""
    lines = [f"VA Signals — {count} bill status update{plural}"]

    for action in actions[:10]:
        bill_type = action.get("bill_type", "")
        bill_number = action.get("bill_number", "")
        bill_ref = f"{bill_type} {bill_number}"

        action_text = action.get("action_text", "")
        if len(action_text) > 80:
            action_text = action_text[:77] + "..."

        action_date = action.get("action_date", "")
        date_str = f" ({action_date})" if action_date else ""

        lines.append(f"- {bill_ref}: {action_text}{date_str}")

    if count > 10:
        lines.append(f"(+{count - 10} more)")

    return {"text": "\n".join(lines)}
