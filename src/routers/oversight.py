"""Oversight monitor endpoints."""

import logging

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..auth.models import UserRole
from ..auth.rbac import RoleChecker
from ..db import connect, table_exists
from ..oversight.db_helpers import get_oversight_events, get_oversight_stats

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Oversight"])


# --- Pydantic Models ---


class OversightEvent(BaseModel):
    event_id: str
    title: str
    primary_source_type: str
    primary_url: str
    pub_timestamp: str | None
    is_escalation: bool
    is_deviation: bool
    surfaced: bool
    surfaced_at: str | None
    fetched_at: str


class OversightEventsResponse(BaseModel):
    events: list[OversightEvent]
    count: int


class OversightStatsResponse(BaseModel):
    total_events: int
    escalations: int
    deviations: int
    surfaced: int
    last_event_at: str | None
    by_source: dict[str, int]


# --- Endpoints ---


@router.get("/api/oversight/stats", response_model=OversightStatsResponse)
def get_oversight_stats_endpoint(_: None = Depends(RoleChecker(UserRole.VIEWER))):
    """Get oversight monitor aggregate statistics."""
    con = connect()
    if not table_exists(con, "om_events"):
        con.close()
        return OversightStatsResponse(
            total_events=0,
            escalations=0,
            deviations=0,
            surfaced=0,
            last_event_at=None,
            by_source={},
        )
    con.close()
    stats = get_oversight_stats()
    return OversightStatsResponse(**stats)


@router.get("/api/oversight/events", response_model=OversightEventsResponse)
def get_oversight_events_endpoint(
    limit: int = Query(50, ge=1, le=500, description="Max events to return"),
    source_type: str | None = Query(None, description="Filter by source type"),
    escalations_only: bool = Query(False, description="Only escalation events"),
    deviations_only: bool = Query(False, description="Only deviation events"),
    surfaced_only: bool = Query(False, description="Only surfaced events"),
    _: None = Depends(RoleChecker(UserRole.ANALYST)),
):
    """Get recent oversight monitor events."""
    con = connect()
    if not table_exists(con, "om_events"):
        con.close()
        return OversightEventsResponse(events=[], count=0)
    con.close()
    events = get_oversight_events(
        limit=limit,
        source_type=source_type,
        escalations_only=escalations_only,
        deviations_only=deviations_only,
        surfaced_only=surfaced_only,
    )
    return OversightEventsResponse(
        events=[OversightEvent(**e) for e in events],
        count=len(events),
    )
