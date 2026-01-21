"""Slack alert formatter for signal triggers."""

from typing import Any
from src.signals.engine.evaluator import EvaluationResult


def format_slack_alert(
    event_id: str,
    authority_id: str,
    indicator_id: str,
    trigger_id: str,
    severity: str,
    title: str,
    result: EvaluationResult,
    source_url: str = None,
    human_review_required: bool = False,
) -> dict:
    """Format a trigger fire as Slack blocks."""

    # Severity emoji
    severity_emoji = {
        "low": "\U0001F535",  # blue circle
        "medium": "\U0001F7E1",  # yellow circle
        "high": "\U0001F7E0",  # orange circle
        "critical": "\U0001F534",  # red circle
    }.get(severity, "\u26AA")  # white circle

    # Build header
    header_text = f"{severity_emoji} [{severity.upper()}] {trigger_id}"

    # Build context
    context_elements = [
        f"*Indicator:* {indicator_id}",
        f"*Authority:* {authority_id}",
    ]
    if result.matched_terms:
        context_elements.append(f"*Matched:* {', '.join(result.matched_terms[:5])}")
    if result.matched_discriminators:
        context_elements.append(f"*Discriminators:* {', '.join(result.matched_discriminators[:3])}")

    # Build blocks
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": header_text, "emoji": True}
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": title[:200]}
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": elem} for elem in context_elements]
        },
    ]

    # Add source link if available
    if source_url:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"<{source_url}|View Source>"}
        })

    # Add review notice if required
    if human_review_required:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\u26A0\uFE0F *Human review required*"}
        })

    return {
        "text": f"{severity_emoji} {trigger_id}: {title[:100]}",  # Fallback text
        "blocks": blocks,
    }


def send_slack_alert(
    channel: str,
    payload: dict,
) -> bool:
    """Send alert to Slack channel. Uses existing notify_slack infrastructure."""
    # Import here to avoid circular dependency
    from src.notify_slack import post_slack

    try:
        # Build the merged payload with blocks
        merged_payload = {"text": payload["text"]}
        if "blocks" in payload:
            merged_payload["blocks"] = payload["blocks"]
        post_slack(merged_payload)
        return True
    except Exception:
        return False
