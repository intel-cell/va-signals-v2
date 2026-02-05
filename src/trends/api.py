"""
Trend Analysis API Router

Provides REST endpoints for accessing historical trend data.
"""

from fastapi import APIRouter, Query, Depends

from ..auth.rbac import RoleChecker
from ..auth.models import UserRole
from .queries import (
    get_signal_trends,
    get_signal_trends_summary,
    get_source_health_trends,
    get_source_health_summary,
    get_oversight_trends,
    get_battlefield_trends,
    get_battlefield_trends_summary,
)

router = APIRouter(prefix="/api/trends", tags=["Trends"])


@router.get("/signals", dependencies=[Depends(RoleChecker(UserRole.ANALYST))])
async def api_signal_trends(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to look back"),
    trigger_id: str | None = Query(default=None, description="Filter by trigger ID"),
):
    """
    Get signal firing trends over time.

    Returns daily signal counts by trigger.
    """
    return get_signal_trends(days=days, trigger_id=trigger_id)


@router.get("/signals/summary", dependencies=[Depends(RoleChecker(UserRole.ANALYST))])
async def api_signal_trends_summary(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to analyze"),
):
    """
    Get signal trend summary statistics.

    Returns totals, averages, and top triggers.
    """
    return get_signal_trends_summary(days=days)


@router.get("/sources", dependencies=[Depends(RoleChecker(UserRole.ANALYST))])
async def api_source_health_trends(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to look back"),
    source_id: str | None = Query(default=None, description="Filter by source ID"),
):
    """
    Get source health metrics over time.

    Returns daily health metrics per source.
    """
    return get_source_health_trends(days=days, source_id=source_id)


@router.get("/sources/summary", dependencies=[Depends(RoleChecker(UserRole.ANALYST))])
async def api_source_health_summary(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to analyze"),
):
    """
    Get source health summary.

    Returns per-source statistics for the period.
    """
    return get_source_health_summary(days=days)


@router.get("/oversight", dependencies=[Depends(RoleChecker(UserRole.ANALYST))])
async def api_oversight_trends(
    weeks: int = Query(default=12, ge=1, le=52, description="Number of weeks to look back"),
):
    """
    Get weekly oversight event trends.

    Returns weekly oversight summaries.
    """
    return get_oversight_trends(weeks=weeks)


@router.get("/battlefield", dependencies=[Depends(RoleChecker(UserRole.ANALYST))])
async def api_battlefield_trends(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to look back"),
):
    """
    Get daily battlefield status trends.

    Returns vehicle counts and gate alerts over time.
    """
    return get_battlefield_trends(days=days)


@router.get("/battlefield/summary", dependencies=[Depends(RoleChecker(UserRole.ANALYST))])
async def api_battlefield_summary(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to analyze"),
):
    """
    Get battlefield trends summary.

    Returns current status and trend statistics.
    """
    return get_battlefield_trends_summary(days=days)
