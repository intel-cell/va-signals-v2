"""Health check and dead-man's switch endpoints."""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..auth.models import UserRole
from ..auth.rbac import RoleChecker
from ..db import connect, execute, table_exists
from ..notify_email import check_smtp_health
from ..resilience.circuit_breaker import (
    congress_api_cb,
    database_cb,
    federal_register_cb,
    lda_gov_cb,
    newsapi_cb,
    omb_cb,
    oversight_cb,
    reginfo_cb,
    va_pubs_cb,
    whitehouse_cb,
)
from ..resilience.staleness_monitor import check_all_sources, get_failure_rate, load_expectations
from ._helpers import utc_now_iso

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])


# --- Pydantic Models ---


class SourceHealth(BaseModel):
    source_id: str
    last_success_at: str | None
    hours_since_success: float | None
    last_run_status: str | None


class EmailHealth(BaseModel):
    configured: bool
    reachable: bool
    error: str | None


class CircuitBreakerStatus(BaseModel):
    name: str
    state: str  # "closed", "open", "half_open"
    failure_count: int
    success_count: int
    rejected_calls: int
    last_failure_at: str | None


class HealthResponse(BaseModel):
    sources: list[SourceHealth]
    email: EmailHealth | None = None
    circuit_breakers: list[CircuitBreakerStatus] = []
    checked_at: str


class PipelineStaleness(BaseModel):
    pipeline: str
    last_activity_at: str | None
    hours_since_activity: float | None
    status: str  # "healthy", "degraded", "critical"


class DeadManResponse(BaseModel):
    pipelines: list[PipelineStaleness]
    overall_status: str  # worst status across all pipelines
    checked_at: str


# --- Endpoints ---


@router.get("/api/health", response_model=HealthResponse)
def get_health(_: None = Depends(RoleChecker(UserRole.VIEWER))):
    """Get health status for each source. Requires VIEWER role."""
    con = connect()

    # Get distinct source IDs
    cur = execute(con, "SELECT DISTINCT source_id FROM source_runs")
    source_ids = [row[0] for row in cur.fetchall()]

    now = datetime.now(UTC)
    sources: list[SourceHealth] = []

    for source_id in source_ids:
        # Last successful run
        cur = execute(
            con,
            """
            SELECT ended_at FROM source_runs
            WHERE source_id = :source_id AND status = 'SUCCESS'
            ORDER BY ended_at DESC LIMIT 1
            """,
            {"source_id": source_id},
        )
        success_row = cur.fetchone()

        # Last run (any status)
        cur = execute(
            con,
            """
            SELECT status FROM source_runs
            WHERE source_id = :source_id
            ORDER BY ended_at DESC LIMIT 1
            """,
            {"source_id": source_id},
        )
        last_row = cur.fetchone()

        last_success_at = success_row[0] if success_row else None
        hours_since_success = None

        if last_success_at:
            try:
                # Handle both ISO formats
                ts = last_success_at.replace("Z", "+00:00")
                last_dt = datetime.fromisoformat(ts)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=UTC)
                delta = now - last_dt
                hours_since_success = round(delta.total_seconds() / 3600, 2)
            except (ValueError, TypeError):
                pass

        sources.append(
            SourceHealth(
                source_id=source_id,
                last_success_at=last_success_at,
                hours_since_success=hours_since_success,
                last_run_status=last_row[0] if last_row else None,
            )
        )

    con.close()

    # Check email SMTP health
    smtp_status = check_smtp_health()
    email_health = EmailHealth(
        configured=smtp_status["configured"],
        reachable=smtp_status["reachable"],
        error=smtp_status.get("error"),
    )

    # Collect circuit breaker states
    all_cbs = [
        federal_register_cb,
        congress_api_cb,
        database_cb,
        lda_gov_cb,
        whitehouse_cb,
        omb_cb,
        va_pubs_cb,
        reginfo_cb,
        oversight_cb,
        newsapi_cb,
    ]
    cb_statuses = []
    for cb in all_cbs:
        last_fail = None
        if cb._metrics.last_failure_time:
            last_fail = datetime.fromtimestamp(cb._metrics.last_failure_time, tz=UTC).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        cb_statuses.append(
            CircuitBreakerStatus(
                name=cb.name,
                state=cb.state.value,
                failure_count=cb._metrics.failed_calls,
                success_count=cb._metrics.successful_calls,
                rejected_calls=cb._metrics.rejected_calls,
                last_failure_at=last_fail,
            )
        )

    return HealthResponse(
        sources=sources,
        email=email_health,
        circuit_breakers=cb_statuses,
        checked_at=utc_now_iso(),
    )


@router.get("/api/health/deadman", response_model=DeadManResponse, tags=["Health"])
def get_deadman_switch(_: None = Depends(RoleChecker(UserRole.VIEWER))):
    """Dead-man's switch: flag pipelines with no recent activity.

    Checks MAX timestamps from key tables and classifies each pipeline as:
    - healthy: activity within the last 24 hours
    - degraded: activity between 24-48 hours ago
    - critical: no activity for over 48 hours (or table missing)
    """
    con = connect()
    now = datetime.now(UTC)

    pipeline_queries = {
        "oversight": ("om_events", "MAX(fetched_at)"),
        "federal_register": ("fr_seen", "MAX(first_seen_at)"),
        "state_intelligence": ("state_signals", "MAX(fetched_at)"),
        "pipeline_runs": ("source_runs", "MAX(ended_at)"),
    }

    pipelines: list[PipelineStaleness] = []

    for pipeline_name, (tbl, agg_expr) in pipeline_queries.items():
        if not table_exists(con, tbl):
            pipelines.append(
                PipelineStaleness(
                    pipeline=pipeline_name,
                    last_activity_at=None,
                    hours_since_activity=None,
                    status="critical",
                )
            )
            continue

        # For pipeline_runs, only count successful runs
        if tbl == "source_runs":
            cur = execute(con, f"SELECT {agg_expr} FROM {tbl} WHERE status = 'SUCCESS'")
        else:
            cur = execute(con, f"SELECT {agg_expr} FROM {tbl}")

        row = cur.fetchone()
        last_ts = row[0] if row else None

        if not last_ts:
            pipelines.append(
                PipelineStaleness(
                    pipeline=pipeline_name,
                    last_activity_at=None,
                    hours_since_activity=None,
                    status="critical",
                )
            )
            continue

        try:
            ts = last_ts.replace("Z", "+00:00")
            last_dt = datetime.fromisoformat(ts)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=UTC)
            hours = round((now - last_dt).total_seconds() / 3600, 2)
        except (ValueError, TypeError):
            hours = None

        if hours is None:
            status = "critical"
        elif hours < 24:
            status = "healthy"
        elif hours < 48:
            status = "degraded"
        else:
            status = "critical"

        pipelines.append(
            PipelineStaleness(
                pipeline=pipeline_name,
                last_activity_at=last_ts,
                hours_since_activity=hours,
                status=status,
            )
        )

    con.close()

    # Overall status is the worst across all pipelines
    status_priority = {"critical": 2, "degraded": 1, "healthy": 0}
    overall = max(pipelines, key=lambda p: status_priority.get(p.status, 0))

    return DeadManResponse(
        pipelines=pipelines,
        overall_status=overall.status,
        checked_at=utc_now_iso(),
    )


# --- Staleness Detection Models ---


class StalenessAlert(BaseModel):
    source_id: str
    last_success_at: str | None
    hours_overdue: float | None
    consecutive_failures: int
    severity: str
    is_critical_source: bool
    message: str


class StalenessResponse(BaseModel):
    alerts: list[StalenessAlert]
    sources_checked: int
    overall_status: str  # worst severity or "healthy"
    checked_at: str


@router.get("/api/health/staleness", response_model=StalenessResponse, tags=["Health"])
def get_staleness_alerts(
    severity: str | None = Query(None, description="Filter by severity: warning, alert, critical"),
    _: None = Depends(RoleChecker(UserRole.VIEWER)),
):
    """Get expected-but-missing signal alerts per source."""
    expectations = load_expectations()
    alerts = check_all_sources()

    if severity:
        alerts = [a for a in alerts if a.severity == severity]

    severity_priority = {"critical": 2, "alert": 1, "warning": 0}
    if alerts:
        worst = max(alerts, key=lambda a: severity_priority.get(a.severity, 0))
        overall_status = worst.severity
    else:
        overall_status = "healthy"

    return StalenessResponse(
        alerts=[
            StalenessAlert(
                source_id=a.source_id,
                last_success_at=a.last_success_at,
                hours_overdue=a.hours_overdue,
                consecutive_failures=a.consecutive_failures,
                severity=a.severity,
                is_critical_source=a.is_critical_source,
                message=a.message,
            )
            for a in alerts
        ],
        sources_checked=len(expectations),
        overall_status=overall_status,
        checked_at=utc_now_iso(),
    )


# --- Source SLA Health (green/yellow/red) ---


class SourceSLAHealth(BaseModel):
    source_id: str
    status: str  # "green", "yellow", "red"
    last_success_at: str | None
    hours_since_success: float | None
    failure_rate_24h: float | None
    total_runs_24h: int
    sla_tolerance_hours: float | None
    sla_alert_after_hours: float | None
    is_critical: bool


class SourceSLAResponse(BaseModel):
    sources: list[SourceSLAHealth]
    overall_status: str  # worst status: "green", "yellow", "red"
    checked_at: str


@router.get("/api/health/sla", response_model=SourceSLAResponse, tags=["Health"])
def get_source_sla_health(_: None = Depends(RoleChecker(UserRole.VIEWER))):
    """Source health with green/yellow/red status based on SLA thresholds.

    - green: within SLA tolerance
    - yellow: overdue past tolerance but below alert threshold
    - red: overdue past alert threshold, >50% failure rate, or no data
    """
    expectations = load_expectations()
    con = connect()
    now = datetime.now(UTC)
    sources: list[SourceSLAHealth] = []

    try:
        for exp in expectations:
            # Get last success
            cur = execute(
                con,
                """
                SELECT ended_at FROM source_runs
                WHERE source_id LIKE :pattern AND status = 'SUCCESS'
                ORDER BY ended_at DESC LIMIT 1
                """,
                {"pattern": f"%{exp.source_id}%"},
            )
            row = cur.fetchone()
            last_success_at = row[0] if row else None

            hours_since = None
            if last_success_at:
                try:
                    ts = last_success_at.replace("Z", "+00:00")
                    last_dt = datetime.fromisoformat(ts)
                    if last_dt.tzinfo is None:
                        last_dt = last_dt.replace(tzinfo=UTC)
                    hours_since = round((now - last_dt).total_seconds() / 3600, 2)
                except (ValueError, TypeError):
                    pass

            failure_rate, total_runs = get_failure_rate(exp.source_id, window_hours=24.0, con=con)

            # Determine status
            if last_success_at is None:
                status = "red"
            elif hours_since is not None and hours_since > exp.alert_after_hours:
                status = "red"
            elif failure_rate > 0.5 and total_runs > 0:
                status = "red"
            elif hours_since is not None and hours_since > exp.tolerance_hours:
                status = "yellow"
            else:
                status = "green"

            sources.append(
                SourceSLAHealth(
                    source_id=exp.source_id,
                    status=status,
                    last_success_at=last_success_at,
                    hours_since_success=hours_since,
                    failure_rate_24h=failure_rate if total_runs > 0 else None,
                    total_runs_24h=total_runs,
                    sla_tolerance_hours=exp.tolerance_hours,
                    sla_alert_after_hours=exp.alert_after_hours,
                    is_critical=exp.is_critical,
                )
            )
    finally:
        con.close()

    status_priority = {"red": 2, "yellow": 1, "green": 0}
    if sources:
        overall = max(sources, key=lambda s: status_priority.get(s.status, 0))
        overall_status = overall.status
    else:
        overall_status = "green"

    return SourceSLAResponse(
        sources=sources,
        overall_status=overall_status,
        checked_at=utc_now_iso(),
    )
