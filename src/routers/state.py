"""State intelligence signals endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..auth.models import UserRole
from ..auth.rbac import RoleChecker
from ..state.db_helpers import (
    get_latest_run,
    get_recent_runs,
    get_signal_count_by_severity,
    get_signal_count_by_state,
    get_signals_by_state,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["State"])


# --- Pydantic Models ---


class StateSignal(BaseModel):
    signal_id: str
    state: str
    title: str
    url: str
    severity: str | None = None
    program: str | None = None
    pub_date: str | None = None


class StateSignalsResponse(BaseModel):
    signals: list[StateSignal]
    count: int


class StateRun(BaseModel):
    id: int
    run_type: str
    state: str | None = None
    status: str
    signals_found: int
    high_severity_count: int
    started_at: str
    finished_at: str | None = None


class StateRunsResponse(BaseModel):
    runs: list[StateRun]
    count: int


class StateStatsResponse(BaseModel):
    total_signals: int
    by_state: dict[str, int]
    by_severity: dict[str, int]
    last_run: dict | None = None


# --- Endpoints ---


@router.get("/api/state/signals", response_model=StateSignalsResponse)
def get_state_signals_endpoint(
    state: str | None = Query(None, description="Filter by state code (TX, CA, FL)"),
    severity: str | None = Query(None, description="Filter by severity (high, medium, low)"),
    limit: int = Query(50, ge=1, le=500, description="Max signals to return"),
    _: None = Depends(RoleChecker(UserRole.ANALYST)),
):
    """Get state intelligence signals with optional filters."""
    try:
        signals = get_signals_by_state(
            state=state,
            severity=severity,
            limit=limit,
        )
        # Map to response model format
        signal_list = [
            StateSignal(
                signal_id=s["signal_id"],
                state=s["state"],
                title=s["title"],
                url=s["url"],
                severity=s.get("severity"),
                program=s.get("program"),
                pub_date=s.get("pub_date"),
            )
            for s in signals
        ]
        return StateSignalsResponse(signals=signal_list, count=len(signal_list))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/api/state/runs", response_model=StateRunsResponse)
def get_state_runs_endpoint(
    limit: int = Query(20, ge=1, le=500, description="Max runs to return"),
    _: None = Depends(RoleChecker(UserRole.ANALYST)),
):
    """Get recent state monitoring runs."""
    try:
        runs = get_recent_runs(limit=limit)
        # Map to response model format
        run_list = [
            StateRun(
                id=r["id"],
                run_type=r["run_type"],
                state=r.get("state"),
                status=r["status"],
                signals_found=r["signals_found"],
                high_severity_count=r["high_severity_count"],
                started_at=r["started_at"],
                finished_at=r.get("finished_at"),
            )
            for r in runs
        ]
        return StateRunsResponse(runs=run_list, count=len(run_list))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/api/state/stats", response_model=StateStatsResponse)
def get_state_stats_endpoint(_: None = Depends(RoleChecker(UserRole.VIEWER))):
    """Get state intelligence statistics."""
    try:
        by_state = get_signal_count_by_state()
        return StateStatsResponse(
            total_signals=sum(by_state.values()),
            by_state=by_state,
            by_severity=get_signal_count_by_severity(),
            last_run=get_latest_run(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
