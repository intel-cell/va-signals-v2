"""Weekly digest generator for state intelligence signals.

Usage:
    python -m src.state.digest [--send-email] [--dry-run] [-v]
"""

import argparse
import logging

logger = logging.getLogger(__name__)


def generate_weekly_digest(dry_run: bool = False) -> dict | None:
    """
    Generate weekly digest from unnotified medium/low severity signals.

    Args:
        dry_run: If True, don't mark signals as notified.

    Returns:
        Dict with 'text' key containing formatted digest, or None if no signals.
    """
    from .db_helpers import get_unnotified_signals, mark_signal_notified
    from .notify import format_state_digest

    # Get medium and low severity signals
    medium_signals = get_unnotified_signals(severity="medium")
    low_signals = get_unnotified_signals(severity="low")
    all_signals = medium_signals + low_signals

    logger.info(f"Found {len(medium_signals)} medium, {len(low_signals)} low severity signals")

    if not all_signals:
        return None

    # Group by state
    by_state: dict[str, list[dict]] = {}
    for sig in all_signals:
        state = sig.get("state", "??")
        by_state.setdefault(state, []).append(sig)

    message = format_state_digest(by_state)

    # Mark signals as notified (unless dry run)
    if message and not dry_run:
        for sig in all_signals:
            mark_signal_notified(sig["signal_id"], "weekly_digest")
        logger.info(f"Marked {len(all_signals)} signals as notified")
    elif dry_run:
        logger.info("Dry run - signals not marked as notified")

    return message


def _send_digest_email(digest_text: str) -> bool:
    """
    Send the weekly digest via email.

    Args:
        digest_text: The formatted digest text.

    Returns:
        True if email sent successfully, False otherwise.
    """
    from datetime import datetime, timezone
    from src.notify_email import is_configured, _send_email, _base_html_template, VA_BLUE

    if not is_configured():
        logger.warning("Email not configured, cannot send digest")
        return False

    date_label = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    subject = f"VA Signals — State Intelligence Weekly Digest ({date_label})"

    # Convert text format to simple HTML (preserve newlines, escape HTML)
    import html
    escaped = html.escape(digest_text)
    # Convert markdown-style formatting for email
    # *bold* -> <strong>bold</strong>
    import re
    escaped = re.sub(r'\*([^*]+)\*', r'<strong>\1</strong>', escaped)
    # _italic_ -> <em>italic</em>
    escaped = re.sub(r'_([^_]+)_', r'<em>\1</em>', escaped)
    # <url|text> -> <a href="url">text</a>
    escaped = re.sub(r'&lt;([^|]+)\|([^&]+)&gt;', r'<a href="\1" style="color: #0071bc;">\2</a>', escaped)
    # Newlines to <br>
    html_content = escaped.replace('\n', '<br>\n')

    content = f"""
        <h2 style="margin: 0 0 20px 0; color: {VA_BLUE}; font-size: 18px;">State Intelligence Weekly Digest</h2>
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6;">
            {html_content}
        </div>
    """

    html_email = _base_html_template(subject, content)

    return _send_email(subject, html_email, digest_text)


def main():
    """CLI entry point for state digest generation."""
    parser = argparse.ArgumentParser(
        description="Generate state intelligence weekly digest"
    )
    parser.add_argument(
        "--send-email",
        action="store_true",
        help="Send the digest via email (requires SMTP env vars).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate digest but don't mark signals as notified.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging.",
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Generate digest
    digest = generate_weekly_digest(dry_run=args.dry_run)

    if not digest:
        print("No signals for weekly digest.")
        return

    # Print to stdout
    print("\n" + "=" * 60)
    print("STATE INTELLIGENCE WEEKLY DIGEST")
    print("=" * 60)
    print(digest.get("text", ""))
    print("=" * 60 + "\n")

    # Optionally send email
    if args.send_email:
        digest_text = digest.get("text", "")
        if _send_digest_email(digest_text):
            print("Digest sent via email.")
        else:
            print("Failed to send digest email (check SMTP configuration).")
            exit(1)


if __name__ == "__main__":
    main()
