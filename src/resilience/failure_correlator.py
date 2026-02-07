"""Failure correlation engine.

Detects correlated failures across sources and circuit breakers
to distinguish infrastructure-wide incidents from isolated errors.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from ..db import connect, execute
from .circuit_breaker import CircuitBreaker, CircuitState

logger = logging.getLogger(__name__)


@dataclass
class CorrelatedIncident:
    incident_type: str  # "infrastructure", "source_cluster", "isolated"
    affected_sources: list[str]
    error_count: int
    window_start: datetime
    window_end: datetime
    message: str
    is_cascade: bool = False


def detect_correlated_failures(
    window_minutes: int = 30, min_sources: int = 3
) -> CorrelatedIncident | None:
    """Query source_runs for ERROR status in time window, correlate by source count.

    Args:
        window_minutes: How far back to look for errors.
        min_sources: Minimum distinct sources to classify as infrastructure incident.

    Returns:
        CorrelatedIncident if errors found, None otherwise.
    """
    now = datetime.now(UTC)
    window_start = now - timedelta(minutes=window_minutes)

    con = connect()
    try:
        cur = execute(
            con,
            """
            SELECT source_id, COUNT(*) as err_count
            FROM source_runs
            WHERE status = 'ERROR' AND ended_at >= :cutoff
            GROUP BY source_id
            """,
            {"cutoff": window_start.isoformat()},
        )
        rows = cur.fetchall()
    finally:
        con.close()

    if not rows:
        return None

    affected_sources = [row[0] for row in rows]
    total_errors = sum(row[1] for row in rows)
    source_count = len(affected_sources)

    if source_count >= min_sources:
        incident_type = "infrastructure"
        message = (
            f"Infrastructure incident: {source_count} sources with "
            f"{total_errors} errors in last {window_minutes}min"
        )
    elif source_count >= 2:
        incident_type = "source_cluster"
        message = (
            f"Source cluster failure: {source_count} sources affected "
            f"({', '.join(affected_sources)})"
        )
    else:
        incident_type = "isolated"
        message = f"Isolated failure: {affected_sources[0]} ({total_errors} errors)"

    return CorrelatedIncident(
        incident_type=incident_type,
        affected_sources=affected_sources,
        error_count=total_errors,
        window_start=window_start,
        window_end=now,
        message=message,
    )


def detect_circuit_breaker_cascade(min_open: int = 3) -> CorrelatedIncident | None:
    """Check if multiple circuit breakers are OPEN simultaneously.

    Args:
        min_open: Minimum OPEN circuit breakers to classify as cascade.

    Returns:
        CorrelatedIncident if cascade detected, None otherwise.
    """
    all_cbs = CircuitBreaker.all()
    open_cbs = [name for name, cb in all_cbs.items() if cb.state == CircuitState.OPEN]

    if len(open_cbs) < min_open:
        return None

    now = datetime.now(UTC)
    return CorrelatedIncident(
        incident_type="infrastructure",
        affected_sources=open_cbs,
        error_count=len(open_cbs),
        window_start=now,
        window_end=now,
        message=f"Circuit breaker cascade: {len(open_cbs)} breakers OPEN ({', '.join(open_cbs)})",
        is_cascade=True,
    )


def get_recent_incidents(hours: int = 24) -> list[CorrelatedIncident]:
    """Get all incidents in the last N hours.

    Combines time-window correlated failures and circuit breaker cascades.
    """
    incidents: list[CorrelatedIncident] = []

    # Check for correlated failures in the full window
    window_minutes = hours * 60
    failure_incident = detect_correlated_failures(window_minutes=window_minutes)
    if failure_incident:
        incidents.append(failure_incident)

    # Check for active circuit breaker cascade
    cascade = detect_circuit_breaker_cascade()
    if cascade:
        incidents.append(cascade)

    return incidents


def get_current_incident() -> CorrelatedIncident | None:
    """Get actively ongoing incident if any.

    Uses a short 30-minute window for recent failures and checks
    current circuit breaker state.
    """
    # Check recent failures (last 30 min)
    failure_incident = detect_correlated_failures(window_minutes=30)

    # Check circuit breaker cascade
    cascade = detect_circuit_breaker_cascade()

    # Cascade is more severe, prefer it
    if cascade:
        return cascade
    return failure_incident
