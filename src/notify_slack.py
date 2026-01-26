import requests
from typing import Any, Dict, Optional

from src.secrets import require_env

def post_slack(payload: Dict[str, Any], timeout: int = 5) -> None:
    token = require_env("SLACK_BOT_TOKEN")
    channel = require_env("SLACK_CHANNEL")

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


def format_new_hearings_alert(hearings: list[dict]) -> Optional[Dict[str, Any]]:
    """
    Format new hearings alert for Slack.

    Format: "VA Signals — N new hearing(s) scheduled"
    - Jan 25: HVAC Hearing - Veterans Healthcare Oversight
    - Jan 28: SVAC Hearing - Benefits Modernization

    Args:
        hearings: List of hearing dicts with keys:
            hearing_date, hearing_time, committee_code, committee_name, title, status

    Returns:
        Slack payload dict or None if no hearings
    """
    if not hearings:
        return None

    count = len(hearings)
    plural = "s" if count != 1 else ""
    lines = [f"VA Signals — {count} new hearing{plural} scheduled"]

    for hearing in hearings[:10]:
        # Format date (e.g., "Jan 25")
        date_str = ""
        hearing_date = hearing.get("hearing_date", "")
        if hearing_date:
            try:
                from datetime import datetime
                dt = datetime.strptime(hearing_date, "%Y-%m-%d")
                date_str = dt.strftime("%b %d")
            except (ValueError, TypeError):
                date_str = hearing_date

        # Format committee (HVAC or SVAC)
        committee_code = hearing.get("committee_code", "").lower()
        if committee_code.startswith("h"):
            committee = "HVAC"
        elif committee_code.startswith("s"):
            committee = "SVAC"
        else:
            committee = committee_code.upper()

        # Format title
        title = hearing.get("title", "(No title)")
        if len(title) > 50:
            title = title[:47] + "..."

        # Build line
        line = f"- {date_str}: {committee} Hearing - {title}"
        lines.append(line)

    if count > 10:
        lines.append(f"(+{count - 10} more)")

    return {"text": "\n".join(lines)}


def format_hearing_changes_alert(changes: list[dict]) -> Optional[Dict[str, Any]]:
    """
    Format hearing changes alert for Slack.

    Format: "VA Signals — Hearing updates"
    - HVAC Jan 25: CANCELLED (was Scheduled)
    - SVAC: Rescheduled from Jan 28 to Feb 3

    Args:
        changes: List of change dicts with keys:
            event_id, field_changed, old_value, new_value, hearing_title,
            committee_name, hearing_date

    Returns:
        Slack payload dict or None if no changes
    """
    if not changes:
        return None

    count = len(changes)
    plural = "s" if count != 1 else ""
    lines = [f"VA Signals — {count} hearing update{plural}"]

    for change in changes[:10]:
        # Determine committee abbreviation from committee_name
        committee_name = change.get("committee_name", "")
        if "house" in committee_name.lower():
            committee = "HVAC"
        elif "senate" in committee_name.lower():
            committee = "SVAC"
        else:
            committee = "Committee"

        # Format date
        date_str = ""
        hearing_date = change.get("hearing_date", "")
        if hearing_date:
            try:
                from datetime import datetime
                dt = datetime.strptime(hearing_date, "%Y-%m-%d")
                date_str = dt.strftime("%b %d")
            except (ValueError, TypeError):
                date_str = hearing_date

        field = change.get("field_changed", "")
        old_val = change.get("old_value", "")
        new_val = change.get("new_value", "")

        # Format based on field type
        if field == "status":
            # Status change: "HVAC Jan 25: CANCELLED (was Scheduled)"
            new_status = (new_val or "Unknown").upper()
            old_status = old_val or "Unknown"
            line = f"- {committee} {date_str}: {new_status} (was {old_status})"

        elif field == "hearing_date":
            # Date change: "SVAC: Rescheduled from Jan 28 to Feb 3"
            old_date_str = old_val or "Unknown"
            new_date_str = new_val or "Unknown"
            try:
                from datetime import datetime
                if old_val:
                    old_dt = datetime.strptime(old_val, "%Y-%m-%d")
                    old_date_str = old_dt.strftime("%b %d")
                if new_val:
                    new_dt = datetime.strptime(new_val, "%Y-%m-%d")
                    new_date_str = new_dt.strftime("%b %d")
            except (ValueError, TypeError):
                pass
            line = f"- {committee}: Rescheduled from {old_date_str} to {new_date_str}"

        elif field == "hearing_time":
            # Time change
            old_time = old_val or "TBD"
            new_time = new_val or "TBD"
            line = f"- {committee} {date_str}: Time changed from {old_time} to {new_time}"

        elif field == "location":
            # Location change
            new_loc = new_val or "TBD"
            if len(new_loc) > 30:
                new_loc = new_loc[:27] + "..."
            line = f"- {committee} {date_str}: Location changed to {new_loc}"

        elif field == "title":
            # Title change - show new title
            new_title = new_val or "(No title)"
            if len(new_title) > 40:
                new_title = new_title[:37] + "..."
            line = f"- {committee} {date_str}: Title updated: {new_title}"

        else:
            # Generic change
            line = f"- {committee} {date_str}: {field} changed"

        lines.append(line)

    if count > 10:
        lines.append(f"(+{count - 10} more)")

    return {"text": "\n".join(lines)}
