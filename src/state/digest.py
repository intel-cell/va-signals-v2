"""Weekly digest generator for state intelligence signals."""


def generate_weekly_digest() -> dict | None:
    """
    Generate weekly digest from unnotified medium/low severity signals.

    Returns:
        Slack message dict or None if no signals.
    """
    from .db_helpers import get_unnotified_signals, mark_signal_notified
    from .notify import format_state_digest

    # Get medium and low severity signals
    medium_signals = get_unnotified_signals(severity="medium")
    low_signals = get_unnotified_signals(severity="low")
    all_signals = medium_signals + low_signals

    if not all_signals:
        return None

    # Group by state
    by_state: dict[str, list[dict]] = {}
    for sig in all_signals:
        state = sig.get("state", "??")
        by_state.setdefault(state, []).append(sig)

    message = format_state_digest(by_state)

    # Mark signals as notified
    if message:
        for sig in all_signals:
            mark_signal_notified(sig["signal_id"], "weekly_digest")

    return message
