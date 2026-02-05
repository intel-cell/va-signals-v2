"""Main runner orchestrator for State Intelligence.

Orchestrates twice-daily monitoring runs for TX, CA, FL, PA, OH, NY.
"""

import argparse
import logging
from datetime import datetime, timezone
from typing import Optional

from src.state.classify import classify_by_keywords, classify_by_llm, ClassificationResult
from src.state.common import RawSignal, generate_signal_id, detect_program
from src.state.db_helpers import (
    insert_state_signal,
    insert_state_classification,
    start_state_run,
    finish_state_run,
    update_source_health,
    signal_exists,
    get_unnotified_signals,
    mark_signal_notified,
)
from src.state.sources.tx_official import TXOfficialSource
from src.state.sources.ca_official import CAOfficialSource
from src.state.sources.fl_official import FLOfficialSource
from src.state.sources.pa_official import PAOfficialSource
from src.state.sources.oh_official import OHOfficialSource
from src.state.sources.ny_official import NYOfficialSource
from src.state.sources.newsapi import NewsAPISource
from src.state.sources.rss import RSSSource
from src.notify_email import is_configured as email_configured, _send_email

logger = logging.getLogger(__name__)

# States we monitor
MONITORED_STATES = ["TX", "CA", "FL", "PA", "OH", "NY"]

def _get_official_source(state: str):
    """Get the official source class for a state. Returns None if not supported."""
    sources = {
        "TX": TXOfficialSource,
        "CA": CAOfficialSource,
        "FL": FLOfficialSource,
        "PA": PAOfficialSource,
        "OH": OHOfficialSource,
        "NY": NYOfficialSource,
    }
    return sources.get(state)


def _get_run_type_from_hour() -> str:
    """Determine run type based on current hour (UTC)."""
    hour = datetime.now(timezone.utc).hour
    # Morning: 6 AM - 2 PM UTC
    if 6 <= hour < 14:
        return "morning"
    return "evening"


def _is_official_source(source_id: str) -> bool:
    """Check if source_id indicates an official source."""
    # Official sources have source_type="official" and contain "official" in source_id
    # or are one of the known official source patterns
    official_patterns = [
        "tvc_news",
        "calvet_news",
        "dva_news",
        "dmva_news",
        "odvs_news",
        "dvs_news",
        "register",
        "oal_register",
        "admin_register",
    ]
    return any(p in source_id for p in official_patterns)


def _classify_signal(signal: RawSignal) -> ClassificationResult:
    """
    Classify a signal using appropriate method.

    - Official sources: keyword classification
    - News sources: LLM classification with keyword fallback
    """
    if _is_official_source(signal.source_id):
        return classify_by_keywords(signal.title, signal.content)
    else:
        return classify_by_llm(signal.title, signal.content, signal.state)


def _fetch_from_source(source, source_name: str) -> tuple[list[RawSignal], bool, Optional[str]]:
    """
    Fetch signals from a source with error handling.

    Returns:
        (signals, success, error_message)
    """
    try:
        signals = source.fetch()
        return signals, True, None
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error(f"Failed to fetch from {source_name}: {error_msg}")
        return [], False, error_msg


def _send_high_severity_notification(signal_data: dict) -> bool:
    """
    Send immediate email notification for high-severity signal.

    Returns True if notification was sent successfully.
    """
    if not email_configured():
        logger.warning("Email not configured, skipping notification")
        return False

    try:
        subject = f"VA Signals - State Alert: {signal_data['state']} - {signal_data['severity'].upper()}"

        html = f"""
        <h2 style="color: #c53030;">State Intelligence Alert</h2>
        <p><strong>State:</strong> {signal_data['state']}</p>
        <p><strong>Title:</strong> {signal_data['title']}</p>
        <p><strong>Severity:</strong> {signal_data['severity'].upper()}</p>
        <p><strong>Source:</strong> {signal_data['source_id']}</p>
        <p><strong>URL:</strong> <a href="{signal_data['url']}">{signal_data['url']}</a></p>
        """

        text = f"""State Intelligence Alert

State: {signal_data['state']}
Title: {signal_data['title']}
Severity: {signal_data['severity'].upper()}
Source: {signal_data['source_id']}
URL: {signal_data['url']}
"""
        return _send_email(subject, html, text)
    except Exception as e:
        logger.error(f"Failed to send email notification: {e}")
        return False


def run_state_monitor(
    run_type: str,
    state: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """
    Main entry point for state monitoring.

    Args:
        run_type: "morning" or "evening"
        state: Optional single state to run (TX, CA, or FL)
        dry_run: If True, log but don't send notifications

    Returns:
        Summary dict with run statistics
    """
    # Determine which states to process
    states_to_process = [state] if state else MONITORED_STATES

    # Record run start
    run_id = start_state_run(run_type=run_type, state=state)
    logger.info(f"Started state monitor run {run_id} (type={run_type}, state={state or 'all'}, dry_run={dry_run})")

    # Tracking
    total_signals_found = 0
    high_severity_count = 0
    new_signals_count = 0
    source_successes = 0
    source_failures = 0
    errors = []

    for st in states_to_process:
        logger.info(f"Processing state: {st}")

        # Collect all raw signals for this state
        raw_signals: list[RawSignal] = []

        # 1. Fetch from official source
        source_class = _get_official_source(st)
        if source_class is not None:
            source = source_class()
            signals, success, error = _fetch_from_source(source, f"{st} official")
            update_source_health(source.source_id, success=success, error=error)
            if success:
                raw_signals.extend(signals)
                source_successes += 1
                logger.info(f"  {st} official: {len(signals)} signals")
            else:
                source_failures += 1
                errors.append(f"{st} official: {error}")

        # 2. Fetch from NewsAPI
        try:
            newsapi_source = NewsAPISource(st)
            signals, success, error = _fetch_from_source(newsapi_source, f"{st} NewsAPI")
            update_source_health(newsapi_source.source_id, success=success, error=error)
            if success:
                raw_signals.extend(signals)
                source_successes += 1
                logger.info(f"  {st} NewsAPI: {len(signals)} signals")
            else:
                source_failures += 1
                errors.append(f"{st} NewsAPI: {error}")
        except ValueError as e:
            logger.warning(f"Could not initialize NewsAPI for {st}: {e}")
            source_failures += 1
            errors.append(f"{st} NewsAPI init: {str(e)}")

        # 3. Fetch from RSS feeds
        try:
            rss_source = RSSSource(st)
            signals, success, error = _fetch_from_source(rss_source, f"{st} RSS")
            update_source_health(rss_source.source_id, success=success, error=error)
            if success:
                raw_signals.extend(signals)
                source_successes += 1
                logger.info(f"  {st} RSS: {len(signals)} signals")
            else:
                source_failures += 1
                errors.append(f"{st} RSS: {error}")
        except ValueError as e:
            logger.warning(f"Could not initialize RSS for {st}: {e}")
            source_failures += 1
            errors.append(f"{st} RSS init: {str(e)}")

        # 4. Deduplicate signals by signal_id (URL hash)
        seen_ids: set[str] = set()
        unique_signals: list[RawSignal] = []
        for sig in raw_signals:
            sig_id = generate_signal_id(sig.url)
            if sig_id not in seen_ids:
                seen_ids.add(sig_id)
                unique_signals.append(sig)

        total_signals_found += len(unique_signals)
        logger.info(f"  {st} total unique signals: {len(unique_signals)}")

        # 5. Process each signal
        for sig in unique_signals:
            sig_id = generate_signal_id(sig.url)

            # Skip if already in database
            if signal_exists(sig_id):
                continue

            new_signals_count += 1

            # Detect program
            text = f"{sig.title} {sig.content or ''}"
            program = detect_program(text)

            # Store signal
            insert_state_signal({
                "signal_id": sig_id,
                "state": sig.state,
                "source_id": sig.source_id,
                "program": program,
                "title": sig.title,
                "content": sig.content,
                "url": sig.url,
                "pub_date": sig.pub_date,
                "event_date": sig.event_date,
            })

            # Classify signal
            classification = _classify_signal(sig)

            # Store classification
            insert_state_classification({
                "signal_id": sig_id,
                "severity": classification.severity,
                "classification_method": classification.method,
                "keywords_matched": ",".join(classification.keywords_matched) if classification.keywords_matched else None,
                "llm_reasoning": classification.llm_reasoning,
            })

            # Track high severity
            if classification.severity == "high":
                high_severity_count += 1
                logger.info(f"  HIGH SEVERITY: {sig.title[:60]}...")

    # 6. Route notifications
    if not dry_run:
        # Get unnotified high-severity signals and send immediate Slack
        high_severity_signals = get_unnotified_signals(severity="high")
        for sig_data in high_severity_signals:
            if _send_high_severity_notification(sig_data):
                mark_signal_notified(sig_data["signal_id"], "email")
                logger.info(f"Sent email notification for {sig_data['signal_id']}")

        # Medium/low severity signals are left for weekly digest
        # (mark_signal_notified is NOT called for them here)
    else:
        logger.info("Dry run - skipping notifications")

    # 7. Determine final status
    if source_successes == 0 and source_failures > 0:
        status = "ERROR"
    elif source_failures > 0:
        status = "PARTIAL"
    else:
        status = "SUCCESS"

    # 8. Record run completion
    finish_state_run(
        run_id=run_id,
        status=status,
        signals_found=new_signals_count,
        high_severity_count=high_severity_count,
    )

    summary = {
        "run_id": run_id,
        "run_type": run_type,
        "state": state,
        "status": status,
        "total_signals_found": total_signals_found,
        "new_signals": new_signals_count,
        "high_severity_count": high_severity_count,
        "source_successes": source_successes,
        "source_failures": source_failures,
        "errors": errors,
        "dry_run": dry_run,
    }

    logger.info(f"Completed run {run_id}: status={status}, new={new_signals_count}, high={high_severity_count}")
    return summary


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="State Intelligence monitoring runner"
    )
    parser.add_argument(
        "--run-type",
        choices=["morning", "evening"],
        default=None,
        help="Run type (morning or evening). Default: based on current hour.",
    )
    parser.add_argument(
        "--state",
        choices=MONITORED_STATES,
        default=None,
        help="Run for a single state only.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log but don't send notifications.",
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

    # Determine run type
    run_type = args.run_type or _get_run_type_from_hour()

    # Run
    summary = run_state_monitor(
        run_type=run_type,
        state=args.state,
        dry_run=args.dry_run,
    )

    # Print summary
    print(f"\n=== State Monitor Run Summary ===")
    print(f"Run ID:            {summary['run_id']}")
    print(f"Run Type:          {summary['run_type']}")
    print(f"State:             {summary['state'] or 'all'}")
    print(f"Status:            {summary['status']}")
    print(f"Total Signals:     {summary['total_signals_found']}")
    print(f"New Signals:       {summary['new_signals']}")
    print(f"High Severity:     {summary['high_severity_count']}")
    print(f"Sources OK:        {summary['source_successes']}")
    print(f"Sources Failed:    {summary['source_failures']}")
    print(f"Dry Run:           {summary['dry_run']}")

    if summary["errors"]:
        print(f"\nErrors:")
        for err in summary["errors"]:
            print(f"  - {err}")

    # Exit with error code if all sources failed
    if summary["status"] == "ERROR":
        exit(1)


if __name__ == "__main__":
    main()
