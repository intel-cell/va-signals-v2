"""Health check and dead-man's switch endpoints."""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..db import connect, execute, table_exists
from ..notify_email import check_smtp_health
from ..auth.rbac import RoleChecker
from ..auth.models import UserRole
from ._helpers import utc_now_iso

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])


# --- Pydantic Models ---

class SourceHealth(BaseModel):
    source_id: str
    last_success_at: Optional[str]
    hours_since_success: Optional[float]
    last_run_status: Optional[str]


class EmailHealth(BaseModel):
    configured: bool
    reachable: bool
    error: Optional[str]


class HealthResponse(BaseModel):
    sources: list[SourceHealth]
    email: Optional[EmailHealth] = None
    checked_at: str


class PipelineStaleness(BaseModel):
    pipeline: str
    last_activity_at: Optional[str]
    hours_since_activity: Optional[float]
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

    now = datetime.now(timezone.utc)
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
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
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

    return HealthResponse(sources=sources, email=email_health, checked_at=utc_now_iso())


@router.get("/api/health/deadman", response_model=DeadManResponse, tags=["Health"])
def get_deadman_switch(_: None = Depends(RoleChecker(UserRole.VIEWER))):
    """Dead-man's switch: flag pipelines with no recent activity.

    Checks MAX timestamps from key tables and classifies each pipeline as:
    - healthy: activity within the last 24 hours
    - degraded: activity between 24-48 hours ago
    - critical: no activity for over 48 hours (or table missing)
    """
    con = connect()
    now = datetime.now(timezone.utc)

    pipeline_queries = {
        "oversight": ("om_events", "MAX(fetched_at)"),
        "federal_register": ("fr_seen", "MAX(first_seen_at)"),
        "state_intelligence": ("state_signals", "MAX(fetched_at)"),
        "pipeline_runs": ("source_runs", "MAX(ended_at)"),
    }

    pipelines: list[PipelineStaleness] = []

    for pipeline_name, (tbl, agg_expr) in pipeline_queries.items():
        if not table_exists(con, tbl):
            pipelines.append(PipelineStaleness(
                pipeline=pipeline_name,
                last_activity_at=None,
                hours_since_activity=None,
                status="critical",
            ))
            continue

        # For pipeline_runs, only count successful runs
        if tbl == "source_runs":
            cur = execute(con, f"SELECT {agg_expr} FROM {tbl} WHERE status = 'SUCCESS'")
        else:
            cur = execute(con, f"SELECT {agg_expr} FROM {tbl}")

        row = cur.fetchone()
        last_ts = row[0] if row else None

        if not last_ts:
            pipelines.append(PipelineStaleness(
                pipeline=pipeline_name,
                last_activity_at=None,
                hours_since_activity=None,
                status="critical",
            ))
            continue

        try:
            ts = last_ts.replace("Z", "+00:00")
            last_dt = datetime.fromisoformat(ts)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
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

        pipelines.append(PipelineStaleness(
            pipeline=pipeline_name,
            last_activity_at=last_ts,
            hours_since_activity=hours,
            status=status,
        ))

    con.close()

    # Overall status is the worst across all pipelines
    status_priority = {"critical": 2, "degraded": 1, "healthy": 0}
    overall = max(pipelines, key=lambda p: status_priority.get(p.status, 0))

    return DeadManResponse(
        pipelines=pipelines,
        overall_status=overall.status,
        checked_at=utc_now_iso(),
    )
