"""Agenda drift deviation detection endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..auth.models import UserRole
from ..auth.rbac import RoleChecker
from ..db import connect, execute, table_exists
from ._helpers import utc_now_iso

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Agenda Drift"])


# --- Pydantic Models ---


class ADDeviationEvent(BaseModel):
    id: int
    member_id: str
    member_name: str
    hearing_id: str
    utterance_id: str
    cos_dist: float
    zscore: float
    detected_at: str
    note: str | None


class ADDeviationResponse(BaseModel):
    events: list[ADDeviationEvent]
    count: int


class ADMemberStats(BaseModel):
    member_id: str
    name: str
    event_count: int
    avg_zscore: float


# --- Endpoints ---


@router.get("/api/agenda-drift/events", response_model=ADDeviationResponse)
def get_ad_events(
    limit: int = Query(50, ge=1, le=500, description="Number of events to return"),
    min_zscore: float = Query(2.0, description="Minimum z-score filter"),
    _: None = Depends(RoleChecker(UserRole.ANALYST)),
):
    """Get recent agenda drift deviation events. Requires ANALYST role."""
    con = connect()

    # Check if table exists
    if not table_exists(con, "ad_deviation_events"):
        con.close()
        return ADDeviationResponse(events=[], count=0)

    cur = execute(
        con,
        """SELECT e.id, e.member_id, m.name, e.hearing_id, e.utterance_id,
                  e.cos_dist, e.zscore, e.detected_at, e.note
           FROM ad_deviation_events e
           JOIN ad_members m ON e.member_id = m.member_id
           WHERE e.zscore >= :min_zscore
           ORDER BY e.detected_at DESC LIMIT :limit""",
        {"min_zscore": min_zscore, "limit": limit},
    )
    rows = cur.fetchall()

    cur = execute(
        con,
        "SELECT COUNT(*) FROM ad_deviation_events WHERE zscore >= :min_zscore",
        {"min_zscore": min_zscore},
    )
    total = cur.fetchone()[0]
    con.close()

    events = [
        ADDeviationEvent(
            id=r[0],
            member_id=r[1],
            member_name=r[2],
            hearing_id=r[3],
            utterance_id=r[4],
            cos_dist=r[5],
            zscore=r[6],
            detected_at=r[7],
            note=r[8],
        )
        for r in rows
    ]

    return ADDeviationResponse(events=events, count=total)


@router.get("/api/agenda-drift/stats")
def get_ad_stats(_: None = Depends(RoleChecker(UserRole.VIEWER))):
    """Get agenda drift system statistics."""
    con = connect()

    # Check if tables exist
    if not table_exists(con, "ad_members"):
        con.close()
        return {
            "total_members": 0,
            "total_utterances": 0,
            "total_embeddings": 0,
            "members_with_baselines": 0,
            "total_events": 0,
            "members": [],
            "checked_at": utc_now_iso(),
        }

    # Total members
    cur = execute(con, "SELECT COUNT(*) FROM ad_members")
    total_members = cur.fetchone()[0]

    # Total utterances
    cur = execute(con, "SELECT COUNT(*) FROM ad_utterances")
    total_utterances = cur.fetchone()[0]

    # Total embeddings
    cur = execute(con, "SELECT COUNT(*) FROM ad_embeddings")
    total_embeddings = cur.fetchone()[0]

    # Members with baselines
    cur = execute(con, "SELECT COUNT(DISTINCT member_id) FROM ad_baselines")
    members_with_baselines = cur.fetchone()[0]

    # Total events
    cur = execute(con, "SELECT COUNT(*) FROM ad_deviation_events")
    total_events = cur.fetchone()[0]

    # Per-member stats
    cur = execute(
        con,
        """SELECT m.member_id, m.name, COUNT(*) as event_count, AVG(e.zscore) as avg_zscore
           FROM ad_deviation_events e
           JOIN ad_members m ON e.member_id = m.member_id
           GROUP BY m.member_id
           ORDER BY event_count DESC""",
    )
    rows = cur.fetchall()
    con.close()

    members = [
        ADMemberStats(
            member_id=r[0],
            name=r[1],
            event_count=r[2],
            avg_zscore=round(r[3], 2) if r[3] else 0.0,
        )
        for r in rows
    ]

    return {
        "total_members": total_members,
        "total_utterances": total_utterances,
        "total_embeddings": total_embeddings,
        "members_with_baselines": members_with_baselines,
        "total_events": total_events,
        "members": [m.model_dump() for m in members],
        "checked_at": utc_now_iso(),
    }


@router.get("/api/agenda-drift/members/{member_id}/history")
def get_ad_member_history(
    member_id: str,
    limit: int = Query(20, ge=1, le=100, description="Number of events to return"),
    _: None = Depends(RoleChecker(UserRole.ANALYST)),
):
    """Get deviation history for a specific member."""
    con = connect()

    # Check if table exists
    if not table_exists(con, "ad_deviation_events"):
        con.close()
        return {"member_id": member_id, "events": [], "count": 0}

    # Get member name
    cur = execute(
        con,
        "SELECT name FROM ad_members WHERE member_id = :member_id",
        {"member_id": member_id},
    )
    member_row = cur.fetchone()
    if not member_row:
        con.close()
        raise HTTPException(status_code=404, detail="Member not found")

    member_name = member_row[0]

    cur = execute(
        con,
        """SELECT id, hearing_id, utterance_id, cos_dist, zscore, detected_at, note
           FROM ad_deviation_events
           WHERE member_id = :member_id
           ORDER BY detected_at DESC LIMIT :limit""",
        {"member_id": member_id, "limit": limit},
    )
    rows = cur.fetchall()

    cur = execute(
        con,
        "SELECT COUNT(*) FROM ad_deviation_events WHERE member_id = :member_id",
        {"member_id": member_id},
    )
    total = cur.fetchone()[0]
    con.close()

    events = [
        {
            "id": r[0],
            "hearing_id": r[1],
            "utterance_id": r[2],
            "cos_dist": r[3],
            "zscore": r[4],
            "detected_at": r[5],
            "note": r[6],
        }
        for r in rows
    ]

    return {
        "member_id": member_id,
        "member_name": member_name,
        "events": events,
        "count": total,
    }
