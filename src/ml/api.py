"""
API endpoints for predictive scoring.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from ..auth.rbac import RoleChecker
from ..auth.models import UserRole
from ..db import connect, execute
from .models import PredictionConfig, PredictionType, BatchPredictionRequest
from .scoring import SignalScorer, score_batch

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ml", tags=["Machine Learning"])


class ScoreRequest(BaseModel):
    """Request to score a signal."""
    signal_id: Optional[str] = None
    title: str
    content: Optional[str] = None
    source_type: Optional[str] = None
    effective_date: Optional[str] = None
    comments_close_date: Optional[str] = None


class ScoreResponse(BaseModel):
    """Scoring response."""
    signal_id: str
    importance_score: float
    impact_score: float
    urgency_score: float
    overall_risk: str
    overall_score: float
    confidence: float
    recommendations: list[str]


@router.post("/score", response_model=ScoreResponse)
async def score_signal(
    request: ScoreRequest,
    _: None = Depends(RoleChecker(UserRole.ANALYST)),
):
    """
    Score a signal for importance, impact, and urgency.

    Returns risk assessment and recommendations.
    Requires ANALYST role.
    """
    scorer = SignalScorer()

    signal_data = {
        "signal_id": request.signal_id or "adhoc",
        "title": request.title,
        "content": request.content,
        "source_type": request.source_type,
        "effective_date": request.effective_date,
        "comments_close_date": request.comments_close_date,
    }

    result = scorer.score(signal_data)

    return ScoreResponse(
        signal_id=result.signal_id,
        importance_score=result.importance_score,
        impact_score=result.impact_score,
        urgency_score=result.urgency_score,
        overall_risk=result.overall_risk.value,
        overall_score=result.overall_score,
        confidence=result.confidence,
        recommendations=result.recommendations,
    )


@router.get("/score/{signal_type}/{signal_id}", response_model=ScoreResponse)
async def score_existing_signal(
    signal_type: str,
    signal_id: str,
    _: None = Depends(RoleChecker(UserRole.ANALYST)),
):
    """
    Score an existing signal from the database.

    Supported signal types: fr, state, oversight, battlefield
    Requires ANALYST role.
    """
    con = connect()
    signal_data = None

    try:
        if signal_type == "fr":
            cur = execute(
                con,
                """
                SELECT f.doc_id, f.title, s.summary, f.effective_date,
                       f.comments_close_date, 'federal_register' as source_type
                FROM fr_seen f
                LEFT JOIN fr_summaries s ON f.doc_id = s.doc_id
                WHERE f.doc_id = :signal_id
                """,
                {"signal_id": signal_id}
            )
            row = cur.fetchone()
            if row:
                signal_data = {
                    "signal_id": row[0],
                    "title": row[1],
                    "content": row[2],
                    "effective_date": row[3],
                    "comments_close_date": row[4],
                    "source_type": row[5],
                }

        elif signal_type == "state":
            cur = execute(
                con,
                """
                SELECT s.signal_id, s.title, s.content, s.pub_date,
                       ss.source_type
                FROM state_signals s
                JOIN state_sources ss ON s.source_id = ss.source_id
                WHERE s.signal_id = :signal_id
                """,
                {"signal_id": signal_id}
            )
            row = cur.fetchone()
            if row:
                signal_data = {
                    "signal_id": row[0],
                    "title": row[1],
                    "content": row[2],
                    "pub_date": row[3],
                    "source_type": row[4],
                }

        elif signal_type == "oversight":
            cur = execute(
                con,
                """
                SELECT event_id, title, summary, pub_timestamp, primary_source_type
                FROM om_events
                WHERE event_id = :signal_id
                """,
                {"signal_id": signal_id}
            )
            row = cur.fetchone()
            if row:
                signal_data = {
                    "signal_id": row[0],
                    "title": row[1],
                    "content": row[2],
                    "pub_date": row[3],
                    "source_type": row[4],
                }

        elif signal_type == "battlefield":
            cur = execute(
                con,
                """
                SELECT vehicle_id, title, attack_surface, status_date, source_type
                FROM bf_vehicles
                WHERE vehicle_id = :signal_id
                """,
                {"signal_id": signal_id}
            )
            row = cur.fetchone()
            if row:
                signal_data = {
                    "signal_id": row[0],
                    "title": row[1],
                    "content": row[2],
                    "pub_date": row[3],
                    "source_type": row[4] or "battlefield",
                }

        else:
            raise HTTPException(status_code=400, detail=f"Unknown signal type: {signal_type}")

    finally:
        con.close()

    if not signal_data:
        raise HTTPException(status_code=404, detail=f"Signal not found: {signal_id}")

    scorer = SignalScorer()
    result = scorer.score(signal_data)

    return ScoreResponse(
        signal_id=result.signal_id,
        importance_score=result.importance_score,
        impact_score=result.impact_score,
        urgency_score=result.urgency_score,
        overall_risk=result.overall_risk.value,
        overall_score=result.overall_score,
        confidence=result.confidence,
        recommendations=result.recommendations,
    )


@router.post("/score/batch")
async def score_batch_signals(
    request: BatchPredictionRequest,
    _: None = Depends(RoleChecker(UserRole.ANALYST)),
):
    """
    Score multiple signals in batch.

    Provide signal IDs and optional prediction types.
    Requires ANALYST role.
    """
    if len(request.signal_ids) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 signals per batch")

    # For now, just return a placeholder
    # In production, this would query signals and score them
    return {
        "message": "Batch scoring not yet implemented",
        "signal_count": len(request.signal_ids),
        "prediction_types": [pt.value for pt in request.prediction_types]
    }


@router.get("/config")
async def get_scoring_config(_: None = Depends(RoleChecker(UserRole.ANALYST))):
    """Get current scoring configuration."""
    config = PredictionConfig()
    return {
        "model_type": config.model_type,
        "version": config.version,
        "thresholds": {
            "high": config.threshold_high,
            "medium": config.threshold_medium,
            "low": config.threshold_low,
        },
        "features_enabled": config.features_enabled,
        "use_ensemble": config.use_ensemble,
        "confidence_threshold": config.confidence_threshold,
    }


@router.get("/stats")
async def get_scoring_stats(_: None = Depends(RoleChecker(UserRole.VIEWER))):
    """Get scoring statistics."""
    # In production, this would aggregate from scored signals
    return {
        "total_scored": 0,
        "avg_importance": 0.0,
        "avg_impact": 0.0,
        "avg_urgency": 0.0,
        "risk_distribution": {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "minimal": 0,
        },
        "model_version": PredictionConfig().version,
    }
