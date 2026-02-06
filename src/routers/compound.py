"""Compound signals API endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..db.compound import (
    get_compound_signals,
    get_compound_signal,
    resolve_compound_signal,
    get_compound_stats,
)
from ..signals.correlator import CorrelationEngine
from ..auth.rbac import RoleChecker
from ..auth.models import UserRole
from ._helpers import utc_now_iso

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Compound Signals"])


# --- Pydantic Models ---

class MemberEventModel(BaseModel):
    source_type: str
    event_id: str
    title: str
    timestamp: Optional[str] = None


class CompoundSignalModel(BaseModel):
    compound_id: str
    rule_id: str
    severity_score: float
    narrative: str
    temporal_window_hours: int
    member_events: list[MemberEventModel]
    topics: list[str]
    created_at: str
    resolved_at: Optional[str] = None


class CompoundSignalsResponse(BaseModel):
    signals: list[CompoundSignalModel]
    total: int
    limit: int
    offset: int


class CompoundStatsResponse(BaseModel):
    total_signals: int
    unresolved: int
    by_rule: dict[str, int]
    avg_severity: float
    checked_at: str


# --- Endpoints ---

@router.get("/api/compound/signals", response_model=CompoundSignalsResponse)
def list_compound_signals(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    rule_id: Optional[str] = Query(None),
    min_severity: Optional[float] = Query(None, ge=0.0, le=1.0),
    _: None = Depends(RoleChecker(UserRole.VIEWER)),
):
    """List compound signals with optional filtering."""
    signals = get_compound_signals(
        limit=limit, offset=offset, rule_id=rule_id, min_severity=min_severity,
    )
    return CompoundSignalsResponse(
        signals=[CompoundSignalModel(**s) for s in signals],
        total=len(signals),
        limit=limit,
        offset=offset,
    )


@router.get("/api/compound/signals/{compound_id}", response_model=CompoundSignalModel)
def get_compound_signal_detail(
    compound_id: str,
    _: None = Depends(RoleChecker(UserRole.VIEWER)),
):
    """Get a single compound signal by ID."""
    signal = get_compound_signal(compound_id)
    if signal is None:
        raise HTTPException(status_code=404, detail=f"Compound signal {compound_id} not found")
    return CompoundSignalModel(**signal)


@router.post("/api/compound/signals/{compound_id}/resolve")
def resolve_signal(
    compound_id: str,
    _: None = Depends(RoleChecker(UserRole.ANALYST)),
):
    """Mark a compound signal as resolved. Requires ANALYST role."""
    resolved = resolve_compound_signal(compound_id)
    if not resolved:
        raise HTTPException(status_code=404, detail=f"Compound signal {compound_id} not found or already resolved")
    return {"resolved": True, "compound_id": compound_id}


@router.get("/api/compound/stats", response_model=CompoundStatsResponse)
def compound_stats(
    _: None = Depends(RoleChecker(UserRole.VIEWER)),
):
    """Get aggregate compound signal statistics."""
    stats = get_compound_stats()
    return CompoundStatsResponse(
        total_signals=stats["total"],
        unresolved=stats["unresolved"],
        by_rule=stats["by_rule"],
        avg_severity=0.0,  # TODO: compute from DB if needed
        checked_at=utc_now_iso(),
    )


@router.post("/api/compound/run")
def run_correlation_engine(
    _: None = Depends(RoleChecker(UserRole.ANALYST)),
):
    """Trigger correlation engine evaluation manually. Requires ANALYST role."""
    try:
        engine = CorrelationEngine()
        result = engine.run()
        return result
    except Exception as e:
        logger.error(f"Correlation engine error: {e}")
        raise HTTPException(status_code=500, detail=f"Correlation engine error: {str(e)}")
