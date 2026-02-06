"""Staleness detection for expected-but-missing data sources.

Compares actual source_runs timestamps against configured expectations
to detect when periodic signals fail to arrive on schedule.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from src.db import connect, execute

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "source_expectations.yaml"


@dataclass
class SourceExpectation:
    source_id: str
    frequency: str          # "daily", "weekly"
    tolerance_hours: float  # hours past expected before warning
    alert_after_hours: float  # hours past expected before alert/critical
    is_critical: bool


@dataclass
class StaleSourceAlert:
    source_id: str
    last_success_at: Optional[str]
    hours_overdue: Optional[float]
    consecutive_failures: int
    severity: str  # "warning", "alert", "critical"
    is_critical_source: bool
    message: str


def load_expectations(config_path: Path = CONFIG_PATH) -> list[SourceExpectation]:
    """Load source expectations from YAML config."""
    if not config_path.exists():
        return []
    with open(config_path) as f:
        data = yaml.safe_load(f)
    if not data or "sources" not in data:
        return []
    expectations = []
    for source_id, cfg in data["sources"].items():
        expectations.append(SourceExpectation(
            source_id=source_id,
            frequency=cfg.get("frequency", "daily"),
            tolerance_hours=float(cfg.get("tolerance_hours", 6)),
            alert_after_hours=float(cfg.get("alert_after_hours", 24)),
            is_critical=bool(cfg.get("is_critical", False)),
        ))
    return expectations


def get_last_success(source_id: str, con=None) -> Optional[str]:
    """Get the most recent successful run timestamp for a source."""
    close = False
    if con is None:
        con = connect()
        close = True
    try:
        cur = execute(
            con,
            """
            SELECT ended_at FROM source_runs
            WHERE source_id LIKE :pattern AND status = 'SUCCESS'
            ORDER BY ended_at DESC LIMIT 1
            """,
            {"pattern": f"%{source_id}%"},
        )
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        if close:
            con.close()


def get_consecutive_failures(source_id: str, con=None) -> int:
    """Count consecutive non-SUCCESS runs from most recent."""
    close = False
    if con is None:
        con = connect()
        close = True
    try:
        cur = execute(
            con,
            """
            SELECT status FROM source_runs
            WHERE source_id LIKE :pattern
            ORDER BY ended_at DESC
            """,
            {"pattern": f"%{source_id}%"},
        )
        count = 0
        for row in cur.fetchall():
            if row[0] == "SUCCESS":
                break
            count += 1
        return count
    finally:
        if close:
            con.close()


def _parse_timestamp(ts: Optional[str]) -> Optional[datetime]:
    """Parse an ISO timestamp string to a timezone-aware datetime."""
    if ts is None:
        return None
    try:
        ts = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def check_source(expectation: SourceExpectation, con=None) -> Optional[StaleSourceAlert]:
    """Check a single source against its expectation. Returns alert if stale, None if healthy."""
    last_success = get_last_success(expectation.source_id, con=con)
    consecutive_failures = get_consecutive_failures(expectation.source_id, con=con)

    now = datetime.now(timezone.utc)
    hours_overdue = None

    if last_success:
        last_dt = _parse_timestamp(last_success)
        if last_dt:
            hours_since = (now - last_dt).total_seconds() / 3600
            hours_overdue = round(hours_since - expectation.tolerance_hours, 2)
            if hours_overdue < 0:
                hours_overdue = None

    # Determine severity
    severity = None

    if hours_overdue is not None:
        if hours_overdue > 2 * expectation.alert_after_hours:
            severity = "critical"
        elif expectation.is_critical and hours_overdue > expectation.alert_after_hours:
            severity = "critical"
        elif hours_overdue > expectation.alert_after_hours:
            severity = "alert"
        else:
            severity = "warning"

    if consecutive_failures >= 5:
        severity = "critical"
    elif consecutive_failures >= 3 and severity != "critical":
        severity = "alert"

    # No last_success at all means critical
    if last_success is None:
        severity = "critical"
        hours_overdue = None

    if severity is None:
        return None

    # Build message
    if last_success is None:
        message = f"{expectation.source_id}: no successful runs recorded"
    else:
        message = f"{expectation.source_id}: {hours_overdue}h overdue, {consecutive_failures} consecutive failures"

    return StaleSourceAlert(
        source_id=expectation.source_id,
        last_success_at=last_success,
        hours_overdue=hours_overdue,
        consecutive_failures=consecutive_failures,
        severity=severity,
        is_critical_source=expectation.is_critical,
        message=message,
    )


def check_all_sources(config_path: Path = CONFIG_PATH) -> list[StaleSourceAlert]:
    """Check all configured sources and return alerts for stale ones."""
    expectations = load_expectations(config_path)
    con = connect()
    alerts = []
    try:
        for exp in expectations:
            alert = check_source(exp, con=con)
            if alert is not None:
                alerts.append(alert)
    finally:
        con.close()
    return alerts
