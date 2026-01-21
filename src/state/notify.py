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
    Format weekly digest grouped by state, then by program.

    Args:
        signals_by_state: Dict mapping state code to list of signal dicts.
            Each signal should have: title, url, program, severity, pub_date

    Returns:
        Slack message dict with 'text' key, or None if no signals.

    Format:
        *State Intelligence Weekly Digest*

        *Texas*
        _PACT Act_ (2 signals)
        * Signal title 1
        * Signal title 2

        _Community Care_ (1 signal)
        * Signal title 3

        *California*
        ...
    """
    if not signals_by_state:
        return None

    # Filter out empty state lists
    signals_by_state = {k: v for k, v in signals_by_state.items() if v}
    if not signals_by_state:
        return None

    lines = ["*State Intelligence Weekly Digest*", ""]

    for state in sorted(signals_by_state.keys()):
        signals = signals_by_state[state]
        lines.append(f"*{state}*")

        # Group by program
        by_program: dict[str, list[dict]] = {}
        for sig in signals:
            prog = sig.get("program") or "General"
            by_program.setdefault(prog, []).append(sig)

        for program in sorted(by_program.keys()):
            prog_signals = by_program[program]
            count = len(prog_signals)
            plural = "signal" if count == 1 else "signals"
            lines.append(f"_{program}_ ({count} {plural})")

            for sig in prog_signals[:5]:  # Limit to 5 per program
                title = sig.get("title", "Unknown")
                url = sig.get("url", "")
                if url:
                    lines.append(f"  \u2022 <{url}|{title}>")
                else:
                    lines.append(f"  \u2022 {title}")

            if len(prog_signals) > 5:
                lines.append(f"  \u2022 (+{len(prog_signals) - 5} more)")

            lines.append("")  # Blank line between programs

        lines.append("")  # Blank line between states

    return {"text": "\n".join(lines).rstrip()}
