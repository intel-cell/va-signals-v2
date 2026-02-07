"""
Email notification module for VA Signals.

Sends HTML + plain text emails for error alerts and new document notifications.
Uses smtplib with TLS support. All env vars optional - returns False if not configured.

Required env vars for email sending:
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_FROM, EMAIL_TO
"""

import os
import smtplib
import ssl
from datetime import UTC
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import certifi

# VA-themed colors
VA_BLUE = "#003366"
VA_LIGHT_BLUE = "#0071bc"
ERROR_RED = "#c53030"
ERROR_BG = "#fff5f5"
SUCCESS_GREEN = "#2f855a"
GRAY_TEXT = "#666666"
GRAY_BORDER = "#e2e8f0"


def _get_config() -> dict[str, Any]:
    """Get email configuration from environment variables."""
    return {
        "host": os.environ.get("SMTP_HOST", ""),
        "port": int(os.environ.get("SMTP_PORT", "") or "587"),
        "user": os.environ.get("SMTP_USER", ""),
        "password": os.environ.get("SMTP_PASS", ""),
        "from_addr": os.environ.get("EMAIL_FROM", ""),
        "to_addr": os.environ.get("EMAIL_TO", ""),
    }


def is_configured() -> bool:
    """Check if all required email env vars are set."""
    cfg = _get_config()
    required = ["host", "user", "password", "from_addr", "to_addr"]
    return all(cfg.get(k) for k in required)


def _send_email(subject: str, html: str, text: str) -> bool:
    """
    Send an email with HTML and plain text parts.
    Returns True on success, False on failure.
    Does not raise exceptions - follows fail-closed pattern.
    """
    if not is_configured():
        return False

    cfg = _get_config()

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = cfg["from_addr"]
        msg["To"] = cfg["to_addr"]

        # Attach plain text first (fallback), then HTML (preferred)
        msg.attach(MIMEText(text, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))

        # Create secure TLS context with certifi certificates (fixes macOS SSL issues)
        context = ssl.create_default_context(cafile=certifi.where())

        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=30) as server:
            server.starttls(context=context)
            server.login(cfg["user"], cfg["password"])
            # Split multiple recipients by comma
            recipients = [r.strip() for r in cfg["to_addr"].split(",")]
            server.sendmail(cfg["from_addr"], recipients, msg.as_string())

        return True

    except Exception:
        # Fail closed - don't raise, just return False
        return False


def check_smtp_health() -> dict:
    """
    Test SMTP connectivity without sending an email.
    Returns a dict with keys: configured, reachable, error.
    """
    result = {"configured": False, "reachable": False, "error": None}

    if not is_configured():
        result["error"] = "Email not configured (missing env vars)"
        return result

    result["configured"] = True
    cfg = _get_config()

    try:
        context = ssl.create_default_context(cafile=certifi.where())
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=10) as server:
            server.starttls(context=context)
            server.login(cfg["user"], cfg["password"])
            server.noop()
        result["reachable"] = True
    except Exception as exc:
        result["error"] = str(exc)

    return result


def _base_html_template(title: str, content: str, footer: str = "") -> str:
    """Generate base HTML email template with responsive styling."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f7fafc;">
    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #f7fafc;">
        <tr>
            <td style="padding: 20px;">
                <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                    <!-- Header -->
                    <tr>
                        <td style="background-color: {VA_BLUE}; padding: 20px 24px; border-radius: 8px 8px 0 0;">
                            <h1 style="margin: 0; color: #ffffff; font-size: 20px; font-weight: 600;">VA Signals</h1>
                        </td>
                    </tr>
                    <!-- Content -->
                    <tr>
                        <td style="padding: 24px;">
                            {content}
                        </td>
                    </tr>
                    <!-- Footer -->
                    <tr>
                        <td style="padding: 16px 24px; border-top: 1px solid {GRAY_BORDER}; color: #a0aec0; font-size: 12px;">
                            {footer if footer else "VA Signals Notification System"}
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""


def _format_timestamp(iso_str: str) -> str:
    """Format ISO timestamp for display."""
    try:
        # Handle both Z suffix and +00:00 format
        clean = iso_str.replace("Z", "+00:00")
        from datetime import datetime

        dt = datetime.fromisoformat(clean)
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return iso_str


def send_error_alert(source_id: str, errors: list[str], run_record: dict[str, Any]) -> bool:
    """
    Send an error alert email.

    Args:
        source_id: The source identifier (e.g., "govinfo_fr_bulk")
        errors: List of error messages
        run_record: Run record dict with started_at, ended_at, status, records_fetched, errors

    Returns:
        True if email sent successfully, False otherwise
    """
    subject = f"VA Signals — ERROR: {source_id}"

    # Build error list HTML
    error_items = "".join(
        f'<li style="margin-bottom: 8px; color: {ERROR_RED};">{err}</li>' for err in errors
    )

    started = _format_timestamp(run_record.get("started_at", ""))
    ended = _format_timestamp(run_record.get("ended_at", ""))
    records = run_record.get("records_fetched", 0)

    content = f"""
        <div style="background-color: {ERROR_BG}; border-left: 4px solid {ERROR_RED}; padding: 16px; margin-bottom: 20px; border-radius: 4px;">
            <h2 style="margin: 0 0 8px 0; color: {ERROR_RED}; font-size: 18px;">Error Alert</h2>
            <p style="margin: 0; color: {GRAY_TEXT};">An error occurred during data collection.</p>
        </div>

        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="margin-bottom: 20px;">
            <tr>
                <td style="padding: 8px 0; color: {GRAY_TEXT}; width: 140px;">Source:</td>
                <td style="padding: 8px 0; font-weight: 600;">{source_id}</td>
            </tr>
            <tr>
                <td style="padding: 8px 0; color: {GRAY_TEXT};">Started:</td>
                <td style="padding: 8px 0;">{started}</td>
            </tr>
            <tr>
                <td style="padding: 8px 0; color: {GRAY_TEXT};">Ended:</td>
                <td style="padding: 8px 0;">{ended}</td>
            </tr>
            <tr>
                <td style="padding: 8px 0; color: {GRAY_TEXT};">Records Fetched:</td>
                <td style="padding: 8px 0;">{records}</td>
            </tr>
        </table>

        <h3 style="margin: 0 0 12px 0; color: {VA_BLUE}; font-size: 16px;">Error Details</h3>
        <ul style="margin: 0; padding-left: 20px;">
            {error_items}
        </ul>
    """

    html = _base_html_template(subject, content)

    # Plain text version
    error_lines = "\n".join(f"  - {err}" for err in errors)
    text = f"""VA Signals — ERROR ALERT

Source: {source_id}
Status: ERROR
Started: {started}
Ended: {ended}
Records Fetched: {records}

Error Details:
{error_lines}

---
VA Signals Notification System
"""

    return _send_email(subject, html, text)


def send_new_docs_alert(
    source_id: str, docs: list[dict[str, Any]], run_record: dict[str, Any]
) -> bool:
    """
    Send a new documents alert email.

    Args:
        source_id: The source identifier
        docs: List of document dicts with doc_id, first_seen_at, source_url
        run_record: Run record dict

    Returns:
        True if email sent successfully, False otherwise
    """
    n = len(docs)
    subject = f"VA Signals — {n} New Document{'s' if n != 1 else ''} Found"

    # Build document list (show up to 10, with "+X more" if needed)
    max_display = 10
    display_docs = docs[:max_display]
    has_more = n > max_display

    doc_items_html = ""
    for doc in display_docs:
        doc_id = doc.get("doc_id", "Unknown")
        source_url = doc.get("source_url", "")
        first_seen = _format_timestamp(doc.get("first_seen_at", doc.get("retrieved_at", "")))

        if source_url:
            doc_link = f'<a href="{source_url}" style="color: {VA_LIGHT_BLUE}; text-decoration: none;">{doc_id}</a>'
        else:
            doc_link = doc_id

        doc_items_html += f"""
            <tr style="border-bottom: 1px solid {GRAY_BORDER};">
                <td style="padding: 12px 8px 12px 0; font-family: monospace; font-size: 14px;">{doc_link}</td>
                <td style="padding: 12px 0; color: {GRAY_TEXT}; font-size: 13px;">{first_seen}</td>
            </tr>
        """

    more_html = ""
    if has_more:
        more_html = f'<p style="margin: 16px 0 0 0; color: {GRAY_TEXT}; font-style: italic;">+ {n - max_display} more document{"s" if (n - max_display) != 1 else ""}</p>'

    started = _format_timestamp(run_record.get("started_at", ""))
    records = run_record.get("records_fetched", 0)

    content = f"""
        <div style="background-color: #f0fff4; border-left: 4px solid {SUCCESS_GREEN}; padding: 16px; margin-bottom: 20px; border-radius: 4px;">
            <h2 style="margin: 0 0 8px 0; color: {SUCCESS_GREEN}; font-size: 18px;">{n} New Document{"s" if n != 1 else ""} Found</h2>
            <p style="margin: 0; color: {GRAY_TEXT};">New VA-related documents have been detected.</p>
        </div>

        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="margin-bottom: 20px;">
            <tr>
                <td style="padding: 8px 0; color: {GRAY_TEXT}; width: 140px;">Source:</td>
                <td style="padding: 8px 0; font-weight: 600;">{source_id}</td>
            </tr>
            <tr>
                <td style="padding: 8px 0; color: {GRAY_TEXT};">Run Time:</td>
                <td style="padding: 8px 0;">{started}</td>
            </tr>
            <tr>
                <td style="padding: 8px 0; color: {GRAY_TEXT};">Records Scanned:</td>
                <td style="padding: 8px 0;">{records}</td>
            </tr>
        </table>

        <h3 style="margin: 0 0 12px 0; color: {VA_BLUE}; font-size: 16px;">Documents</h3>
        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
            <thead>
                <tr style="border-bottom: 2px solid {GRAY_BORDER};">
                    <th style="padding: 8px 8px 8px 0; text-align: left; color: {GRAY_TEXT}; font-size: 12px; text-transform: uppercase;">Document ID</th>
                    <th style="padding: 8px 0; text-align: left; color: {GRAY_TEXT}; font-size: 12px; text-transform: uppercase;">First Seen</th>
                </tr>
            </thead>
            <tbody>
                {doc_items_html}
            </tbody>
        </table>
        {more_html}
    """

    html = _base_html_template(subject, content)

    # Plain text version
    doc_lines = []
    for doc in display_docs:
        doc_id = doc.get("doc_id", "Unknown")
        source_url = doc.get("source_url", "")
        if source_url:
            doc_lines.append(f"  - {doc_id}\n    {source_url}")
        else:
            doc_lines.append(f"  - {doc_id}")

    more_text = f"\n  + {n - max_display} more" if has_more else ""

    text = f"""VA Signals — {n} New Document{"s" if n != 1 else ""} Found

Source: {source_id}
Run Time: {started}
Records Scanned: {records}

Documents:
{chr(10).join(doc_lines)}{more_text}

---
VA Signals Notification System
"""

    return _send_email(subject, html, text)


def send_daily_digest(
    runs: list[dict[str, Any]],
    new_docs_by_source: dict[str, list[dict[str, Any]]],
    date_label: str = "",
) -> bool:
    """
    Send a daily digest email summarizing the day's runs.

    Args:
        runs: List of run records from the day
        new_docs_by_source: Dict mapping source_id to list of new docs
        date_label: Label for the digest (e.g., "2024-01-15")

    Returns:
        True if email sent successfully, False otherwise
    """
    if not runs:
        return False

    from datetime import datetime

    if not date_label:
        date_label = datetime.now(UTC).strftime("%Y-%m-%d")

    subject = f"VA Signals — Daily Digest for {date_label}"

    # Calculate summary stats
    total_runs = len(runs)
    success_runs = sum(1 for r in runs if r.get("status") == "SUCCESS")
    error_runs = sum(1 for r in runs if r.get("status") == "ERROR")
    no_data_runs = sum(1 for r in runs if r.get("status") == "NO_DATA")
    total_new_docs = sum(len(docs) for docs in new_docs_by_source.values())

    # Build run summary rows
    run_rows = ""
    for run in runs:
        source = run.get("source_id", "Unknown")
        status = run.get("status", "UNKNOWN")
        records = run.get("records_fetched", 0)
        new_count = len(new_docs_by_source.get(source, []))

        status_color = (
            SUCCESS_GREEN
            if status == "SUCCESS"
            else (ERROR_RED if status == "ERROR" else GRAY_TEXT)
        )

        run_rows += f"""
            <tr style="border-bottom: 1px solid {GRAY_BORDER};">
                <td style="padding: 10px 8px 10px 0;">{source}</td>
                <td style="padding: 10px 8px; color: {status_color}; font-weight: 600;">{status}</td>
                <td style="padding: 10px 8px; text-align: right;">{records}</td>
                <td style="padding: 10px 0 10px 8px; text-align: right;">{new_count}</td>
            </tr>
        """

    content = f"""
        <h2 style="margin: 0 0 20px 0; color: {VA_BLUE}; font-size: 18px;">Daily Digest for {date_label}</h2>

        <div style="display: flex; gap: 16px; margin-bottom: 24px;">
            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                <tr>
                    <td style="background-color: #f7fafc; padding: 16px; border-radius: 8px; text-align: center; width: 25%;">
                        <div style="font-size: 24px; font-weight: 700; color: {VA_BLUE};">{total_runs}</div>
                        <div style="font-size: 12px; color: {GRAY_TEXT}; text-transform: uppercase;">Total Runs</div>
                    </td>
                    <td style="width: 8px;"></td>
                    <td style="background-color: #f0fff4; padding: 16px; border-radius: 8px; text-align: center; width: 25%;">
                        <div style="font-size: 24px; font-weight: 700; color: {SUCCESS_GREEN};">{success_runs}</div>
                        <div style="font-size: 12px; color: {GRAY_TEXT}; text-transform: uppercase;">Success</div>
                    </td>
                    <td style="width: 8px;"></td>
                    <td style="background-color: {ERROR_BG}; padding: 16px; border-radius: 8px; text-align: center; width: 25%;">
                        <div style="font-size: 24px; font-weight: 700; color: {ERROR_RED};">{error_runs}</div>
                        <div style="font-size: 12px; color: {GRAY_TEXT}; text-transform: uppercase;">Errors</div>
                    </td>
                    <td style="width: 8px;"></td>
                    <td style="background-color: #f7fafc; padding: 16px; border-radius: 8px; text-align: center; width: 25%;">
                        <div style="font-size: 24px; font-weight: 700; color: {VA_LIGHT_BLUE};">{total_new_docs}</div>
                        <div style="font-size: 12px; color: {GRAY_TEXT}; text-transform: uppercase;">New Docs</div>
                    </td>
                </tr>
            </table>
        </div>

        <h3 style="margin: 0 0 12px 0; color: {VA_BLUE}; font-size: 16px;">Run Summary</h3>
        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
            <thead>
                <tr style="border-bottom: 2px solid {GRAY_BORDER};">
                    <th style="padding: 8px 8px 8px 0; text-align: left; color: {GRAY_TEXT}; font-size: 12px; text-transform: uppercase;">Source</th>
                    <th style="padding: 8px; text-align: left; color: {GRAY_TEXT}; font-size: 12px; text-transform: uppercase;">Status</th>
                    <th style="padding: 8px; text-align: right; color: {GRAY_TEXT}; font-size: 12px; text-transform: uppercase;">Scanned</th>
                    <th style="padding: 8px 0 8px 8px; text-align: right; color: {GRAY_TEXT}; font-size: 12px; text-transform: uppercase;">New</th>
                </tr>
            </thead>
            <tbody>
                {run_rows}
            </tbody>
        </table>
    """

    html = _base_html_template(subject, content)

    # Plain text version
    run_lines = []
    for run in runs:
        source = run.get("source_id", "Unknown")
        status = run.get("status", "UNKNOWN")
        records = run.get("records_fetched", 0)
        new_count = len(new_docs_by_source.get(source, []))
        run_lines.append(f"  {source}: {status} ({records} scanned, {new_count} new)")

    text = f"""VA Signals — Daily Digest for {date_label}

Summary:
  Total Runs: {total_runs}
  Successful: {success_runs}
  Errors: {error_runs}
  No Data: {no_data_runs}
  New Documents: {total_new_docs}

Run Details:
{chr(10).join(run_lines)}

---
VA Signals Notification System
"""

    return _send_email(subject, html, text)
