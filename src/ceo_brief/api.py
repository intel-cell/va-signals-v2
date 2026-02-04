"""
CEO Brief Dashboard API Routes

HOTEL COMMAND - Phase 1 Integration
Exposes CEO Brief system to Command Dashboard.

Endpoints:
- GET /api/ceo-brief/briefs - List CEO briefs
- GET /api/ceo-brief/briefs/latest - Get latest brief
- GET /api/ceo-brief/briefs/{brief_id} - Get specific brief
- POST /api/ceo-brief/generate - Generate new brief (async)
"""

from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Query, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel

from ..auth.rbac import RoleChecker
from ..auth.models import UserRole
from .db_helpers import get_ceo_brief, get_latest_brief, list_briefs


router = APIRouter(prefix="/api/ceo-brief", tags=["ceo-brief"])


# --- Response Models ---

class BriefSummary(BaseModel):
    brief_id: str
    generated_at: str
    period_start: str
    period_end: str
    objective: Optional[str] = None
    status: str


class BriefListResponse(BaseModel):
    briefs: list[BriefSummary]
    count: int


class GenerateResponse(BaseModel):
    status: str
    message: str
    brief_id: Optional[str] = None


# --- Endpoints ---

@router.get("/briefs", response_model=BriefListResponse)
async def list_ceo_briefs(
    limit: int = Query(10, ge=1, le=50, description="Max briefs to return"),
    _: None = Depends(RoleChecker(UserRole.ANALYST)),
):
    """
    List available CEO briefs.

    Returns summary information for each brief.
    Requires ANALYST role or higher.
    """
    briefs = list_briefs(limit=limit)

    return BriefListResponse(
        briefs=[
            BriefSummary(
                brief_id=b["brief_id"],
                generated_at=b["generated_at"],
                period_start=b["period_start"],
                period_end=b["period_end"],
                objective=b.get("objective"),
                status=b.get("status", "complete"),
            )
            for b in briefs
        ],
        count=len(briefs),
    )


@router.get("/briefs/latest")
async def get_latest_ceo_brief(
    _: None = Depends(RoleChecker(UserRole.ANALYST)),
):
    """
    Get the most recent CEO brief.

    Returns full brief with all sections.
    Requires ANALYST role or higher.
    """
    brief = get_latest_brief()
    if not brief:
        raise HTTPException(status_code=404, detail="No briefs available")

    return brief


@router.get("/briefs/{brief_id}")
async def get_ceo_brief_by_id(
    brief_id: str,
    _: None = Depends(RoleChecker(UserRole.ANALYST)),
):
    """
    Get a specific CEO brief by ID.

    Returns full brief with all sections.
    Requires ANALYST role or higher.
    """
    brief = get_ceo_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail="Brief not found")

    return brief


@router.post("/generate", response_model=GenerateResponse)
async def trigger_brief_generation(
    background_tasks: BackgroundTasks,
    _: None = Depends(RoleChecker(UserRole.LEADERSHIP)),
):
    """
    Trigger generation of a new CEO brief.

    This is an async operation - the brief will be generated
    in the background and can be retrieved later.

    Requires LEADERSHIP role or higher.
    """
    from .runner import run_pipeline

    # Generate brief ID
    brief_id = f"brief_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    # Queue background task
    background_tasks.add_task(run_pipeline)

    return GenerateResponse(
        status="queued",
        message="Brief generation started. Check /briefs/latest for results.",
        brief_id=brief_id,
    )
