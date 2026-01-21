"""Output formatters for oversight events - Slack alerts and digests."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class SlackMessage:
    """Slack message with blocks for rich formatting."""

    channel: str
    text: str  # Fallback text
    blocks: list = field(default_factory=list)


def _severity_emoji(severity: str) -> str:
    """Get emoji for severity level."""
    return {
        "critical": "🚨",
        "high": "⚠️",
        "medium": "📋",
        "low": "ℹ️",
    }.get(severity, "📌")


def _source_emoji(source_type: str) -> str:
    """Get emoji for source type."""
    return {
        "gao": "📊",
        "oig": "🔍",
        "committee_press": "🏛️",
        "congressional_record": "📜",
        "news_wire": "📰",
        "cafc": "⚖️",
        "crs": "📚",
    }.get(source_type, "📄")


def format_immediate_alert(event: dict) -> SlackMessage:
    """
    Format an escalation event as a Slack immediate alert.

    Args:
        event: Event dict with escalation signals

    Returns:
        SlackMessage ready to send
    """
    severity = event.get("escalation_severity", "high")
    emoji = _severity_emoji(severity)
    source_emoji = _source_emoji(event.get("primary_source_type", ""))

    title = event.get("title", "Unknown Event")
    url = event.get("primary_url", "")
    signals = event.get("escalation_signals", [])
    summary = event.get("summary", "")[:300]

    # Build fallback text
    signal_text = ", ".join(signals) if signals else "escalation detected"
    text = f"{emoji} [{severity.upper()}] {signal_text}: {title}"

    # Build rich blocks
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{emoji} Oversight Alert: {severity.upper()}",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*<{url}|{title}>*",
            },
        },
    ]

    if signals:
        blocks.append({
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Signals:*\n{', '.join(signals)}"},
                {"type": "mrkdwn", "text": f"*Source:*\n{source_emoji} {event.get('primary_source_type', 'unknown')}"},
            ],
        })

    if summary:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"_{summary}_"},
        })

    blocks.append({
        "type": "context",
        "elements": [
            {"type": "mrkdwn", "text": f"Published: {event.get('pub_timestamp', 'unknown')[:10]}"},
        ],
    })

    return SlackMessage(
        channel="#va-signals",
        text=text,
        blocks=blocks,
    )


def group_events_by_theme(events: list[dict]) -> dict[str, list[dict]]:
    """
    Group events by theme for digest organization.

    Args:
        events: List of event dicts

    Returns:
        Dict of theme -> list of events
    """
    grouped = defaultdict(list)

    for event in events:
        theme = event.get("theme") or "other"
        grouped[theme].append(event)

    return dict(grouped)


def _format_event_line(event: dict) -> str:
    """Format a single event as a digest line."""
    title = event.get("title", "Unknown")
    url = event.get("primary_url", "")
    source = event.get("primary_source_type", "")
    date = event.get("pub_timestamp", "")[:10]

    flags = []
    if event.get("is_escalation"):
        flags.append("🚨 ESCALATION")
    if event.get("is_deviation"):
        flags.append("📈 DEVIATION")

    flag_str = f" [{', '.join(flags)}]" if flags else ""

    return f"• [{source.upper()}] [{date}] {title}{flag_str}\n  {url}"


def format_weekly_digest(
    events: list[dict],
    period_start: str,
    period_end: str,
) -> str:
    """
    Format events as a weekly digest.

    Args:
        events: List of event dicts
        period_start: Start of period (YYYY-MM-DD)
        period_end: End of period (YYYY-MM-DD)

    Returns:
        Formatted digest string
    """
    if not events:
        return f"""# VA Oversight Weekly Digest
## {period_start} to {period_end}

📊 **Summary**: A quiet week with no significant oversight activity flagged.

No escalations or pattern deviations detected during this period.
"""

    # Group by theme
    grouped = group_events_by_theme(events)

    # Count stats
    escalations = sum(1 for e in events if e.get("is_escalation"))
    deviations = sum(1 for e in events if e.get("is_deviation"))

    lines = [
        f"# VA Oversight Weekly Digest",
        f"## {period_start} to {period_end}",
        "",
        f"📊 **Summary**: {len(events)} significant events",
        f"- 🚨 Escalations: {escalations}",
        f"- 📈 Deviations: {deviations}",
        "",
    ]

    # Add events by theme
    for theme, theme_events in sorted(grouped.items()):
        theme_title = theme.replace("_", " ").title()
        lines.append(f"### {theme_title}")
        lines.append("")

        for event in theme_events:
            lines.append(_format_event_line(event))
            lines.append("")

    return "\n".join(lines)


def format_digest_slack(
    events: list[dict],
    period_start: str,
    period_end: str,
) -> SlackMessage:
    """
    Format weekly digest as Slack message.

    Args:
        events: List of event dicts
        period_start: Start of period
        period_end: End of period

    Returns:
        SlackMessage ready to send
    """
    escalations = sum(1 for e in events if e.get("is_escalation"))
    deviations = sum(1 for e in events if e.get("is_deviation"))

    text = f"Weekly Digest ({period_start} to {period_end}): {len(events)} events, {escalations} escalations, {deviations} deviations"

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"📋 VA Oversight Weekly Digest",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{period_start}* to *{period_end}*",
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Total Events:*\n{len(events)}"},
                {"type": "mrkdwn", "text": f"*Escalations:*\n🚨 {escalations}"},
            ],
        },
    ]

    if not events:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "_A quiet week with no significant oversight activity._"},
        })
    else:
        # Add top events
        blocks.append({"type": "divider"})

        for event in events[:5]:  # Top 5
            emoji = "🚨" if event.get("is_escalation") else "📈"
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{emoji} *<{event.get('primary_url', '')}|{event.get('title', '')[:60]}>*",
                },
            })

        if len(events) > 5:
            blocks.append({
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"_...and {len(events) - 5} more events_"},
                ],
            })

    return SlackMessage(
        channel="#va-signals",
        text=text,
        blocks=blocks,
    )
