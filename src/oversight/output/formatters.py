"""Output formatters for oversight events - email alerts and digests."""

from collections import defaultdict


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
        flags.append("ESCALATION")
    if event.get("is_deviation"):
        flags.append("DEVIATION")

    flag_str = f" [{', '.join(flags)}]" if flags else ""

    return f"- [{source.upper()}] [{date}] {title}{flag_str}\n  {url}"


def format_weekly_digest(
    events: list[dict],
    period_start: str,
    period_end: str,
) -> str:
    """
    Format events as a weekly digest (markdown).

    Args:
        events: List of event dicts
        period_start: Start of period (YYYY-MM-DD)
        period_end: End of period (YYYY-MM-DD)

    Returns:
        Formatted digest string (markdown)
    """
    if not events:
        return f"""# VA Oversight Weekly Digest
## {period_start} to {period_end}

**Summary**: A quiet week with no significant oversight activity flagged.

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
        f"**Summary**: {len(events)} significant events",
        f"- Escalations: {escalations}",
        f"- Deviations: {deviations}",
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


def format_escalation_alert(event: dict) -> tuple[str, str, str]:
    """
    Format an escalation event for email notification.

    Args:
        event: Event dict with escalation signals

    Returns:
        Tuple of (subject, html_body, text_body)
    """
    severity = event.get("escalation_severity", "high").upper()
    title = event.get("title", "Unknown Event")
    url = event.get("primary_url", "")
    signals = event.get("escalation_signals", [])
    summary = event.get("summary", "")[:500]
    source = event.get("primary_source_type", "unknown")
    pub_date = event.get("pub_timestamp", "unknown")[:10]

    signal_text = ", ".join(signals) if signals else "escalation detected"

    subject = f"VA Signals - Oversight Alert [{severity}]: {signal_text}"

    html = f"""
    <h2 style="color: #c53030;">Oversight Alert: {severity}</h2>
    <p><strong>Title:</strong> <a href="{url}">{title}</a></p>
    <p><strong>Signals:</strong> {signal_text}</p>
    <p><strong>Source:</strong> {source}</p>
    <p><strong>Published:</strong> {pub_date}</p>
    {"<p><strong>Summary:</strong> " + summary + "</p>" if summary else ""}
    """

    text = f"""Oversight Alert: {severity}

Title: {title}
URL: {url}
Signals: {signal_text}
Source: {source}
Published: {pub_date}
{"Summary: " + summary if summary else ""}
"""

    return subject, html, text
