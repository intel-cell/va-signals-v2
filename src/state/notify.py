"""State-specific notification formatting for Slack alerts."""


def format_state_alert(signals: list[dict]) -> dict | None:
    """
    Format state intelligence signals for Slack.

    Args:
        signals: List of signal dicts with keys:
            - state, title, url, program, source_id
            - classification with severity, keywords_matched

    Returns:
        Slack message dict with 'text' key, or None if no signals.
    """
    if not signals:
        return None

    lines = ["*State Intelligence Alert*", ""]

    for sig in signals:
        state = sig.get("state", "??")
        title = sig.get("title", "Unknown")
        url = sig.get("url", "")
        program = sig.get("program") or "General"
        source_id = sig.get("source_id", "unknown")

        # Keywords can be a string (comma-separated) or list
        keywords = sig.get("keywords_matched")
        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(",") if k.strip()]
        elif not keywords:
            keywords = []

        # Format: • *[State]* Title (linked)
        if url:
            lines.append(f"• *[{state}]* <{url}|{title}>")
        else:
            lines.append(f"• *[{state}]* {title}")

        # Format: _Program_ | Source
        lines.append(f"  _{program}_ | {source_id}")

        # Format: Triggers: keyword1, keyword2
        if keywords:
            lines.append(f"  Triggers: {', '.join(keywords)}")

        lines.append("")  # blank line between signals

    return {"text": "\n".join(lines).strip()}


def format_state_digest(signals_by_state: dict[str, list[dict]]) -> dict | None:
    """
    Format weekly digest grouped by state.

    Args:
        signals_by_state: Dict mapping state code to list of signals

    Returns:
        Slack message dict or None if empty.
    """
    # Implementation for Task 7.2
    pass
