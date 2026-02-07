"""Bills and hearings endpoints."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..auth.models import UserRole
from ..auth.rbac import RoleChecker
from ..db import connect, execute, table_exists

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Bills", "Hearings"])


# --- Pydantic Models ---


class BillResponse(BaseModel):
    bill_id: str
    congress: int
    bill_type: str
    bill_number: int
    title: str
    sponsor_name: str | None
    sponsor_party: str | None
    sponsor_state: str | None
    latest_action_date: str | None
    latest_action_text: str | None
    first_seen_at: str


class BillsResponse(BaseModel):
    bills: list[BillResponse]
    count: int


class BillStatsResponse(BaseModel):
    total_bills: int
    new_this_week: int
    by_type: dict[str, int]
    by_congress: dict[int, int]


class HearingResponse(BaseModel):
    event_id: str
    congress: int
    chamber: str
    committee_name: str | None
    hearing_date: str
    hearing_time: str | None
    title: str | None
    meeting_type: str | None
    status: str
    url: str | None


class HearingsResponse(BaseModel):
    hearings: list[HearingResponse]
    count: int


class HearingStatsResponse(BaseModel):
    total_hearings: int
    upcoming_count: int
    by_committee: dict[str, int]
    by_status: dict[str, int]


# --- Endpoints ---


@router.get("/api/bills", response_model=BillsResponse)
def get_bills(
    limit: int = Query(50, ge=1, le=500, description="Number of bills to return"),
    congress: int | None = Query(None, description="Filter by congress number"),
    _: None = Depends(RoleChecker(UserRole.VIEWER)),
):
    """List tracked VA bills."""
    con = connect()

    try:
        # Check if bills table exists
        if not table_exists(con, "bills"):
            return BillsResponse(bills=[], count=0)

        query = """
            SELECT bill_id, congress, bill_type, bill_number, title,
                   sponsor_name, sponsor_party, sponsor_state,
                   latest_action_date, latest_action_text, first_seen_at
            FROM bills
            WHERE 1=1
        """
        params: dict[str, Any] = {}

        if congress is not None:
            query += " AND congress = :congress"
            params["congress"] = congress

        query += " ORDER BY latest_action_date DESC NULLS LAST, first_seen_at DESC LIMIT :limit"
        params["limit"] = limit

        cur = execute(con, query, params)
        rows = cur.fetchall()

        # Get total count
        count_query = "SELECT COUNT(*) FROM bills"
        if congress is not None:
            count_query += " WHERE congress = :congress"
            cur = execute(con, count_query, {"congress": congress})
        else:
            cur = execute(con, count_query)
        total = cur.fetchone()[0]
    finally:
        con.close()

    bills = [
        BillResponse(
            bill_id=row[0],
            congress=row[1],
            bill_type=row[2],
            bill_number=row[3],
            title=row[4],
            sponsor_name=row[5],
            sponsor_party=row[6],
            sponsor_state=row[7],
            latest_action_date=row[8],
            latest_action_text=row[9],
            first_seen_at=row[10],
        )
        for row in rows
    ]

    return BillsResponse(bills=bills, count=total)


@router.get("/api/bills/stats", response_model=BillStatsResponse)
def get_bill_stats(_: None = Depends(RoleChecker(UserRole.VIEWER))):
    """Get bill summary statistics."""
    con = connect()

    try:
        # Check if bills table exists
        if not table_exists(con, "bills"):
            return BillStatsResponse(total_bills=0, new_this_week=0, by_type={}, by_congress={})

        # Total bills
        cur = execute(con, "SELECT COUNT(*) FROM bills")
        total_bills = cur.fetchone()[0]

        # New this week
        seven_days_ago = (datetime.now(UTC) - timedelta(days=7)).strftime("%Y-%m-%d")
        cur = execute(
            con,
            "SELECT COUNT(*) FROM bills WHERE first_seen_at >= :since",
            {"since": seven_days_ago},
        )
        new_this_week = cur.fetchone()[0]

        # By type
        cur = execute(con, "SELECT bill_type, COUNT(*) FROM bills GROUP BY bill_type")
        by_type = dict(cur.fetchall())

        # By congress
        cur = execute(
            con, "SELECT congress, COUNT(*) FROM bills GROUP BY congress ORDER BY congress DESC"
        )
        by_congress = {int(row[0]): row[1] for row in cur.fetchall()}
    finally:
        con.close()

    return BillStatsResponse(
        total_bills=total_bills,
        new_this_week=new_this_week,
        by_type=by_type,
        by_congress=by_congress,
    )


@router.get("/api/hearings", response_model=HearingsResponse)
def get_hearings(
    upcoming: bool = Query(True, description="Show only upcoming hearings"),
    limit: int = Query(20, ge=1, le=100, description="Number of hearings to return"),
    _: None = Depends(RoleChecker(UserRole.VIEWER)),
):
    """List hearings - default to upcoming only."""
    con = connect()

    try:
        # Check if hearings table exists
        if not table_exists(con, "hearings"):
            return HearingsResponse(hearings=[], count=0)

        today = datetime.now(UTC).strftime("%Y-%m-%d")

        if upcoming:
            query = """
                SELECT event_id, congress, chamber, committee_name, hearing_date,
                       hearing_time, title, meeting_type, status, url
                FROM hearings
                WHERE hearing_date >= :today
                ORDER BY hearing_date ASC, hearing_time ASC
                LIMIT :limit
            """
            cur = execute(con, query, {"today": today, "limit": limit})
        else:
            query = """
                SELECT event_id, congress, chamber, committee_name, hearing_date,
                       hearing_time, title, meeting_type, status, url
                FROM hearings
                ORDER BY hearing_date DESC, hearing_time DESC
                LIMIT :limit
            """
            cur = execute(con, query, {"limit": limit})

        rows = cur.fetchall()

        # Get total count
        if upcoming:
            cur = execute(
                con,
                "SELECT COUNT(*) FROM hearings WHERE hearing_date >= :today",
                {"today": today},
            )
        else:
            cur = execute(con, "SELECT COUNT(*) FROM hearings")
        total = cur.fetchone()[0]
    finally:
        con.close()

    hearings = [
        HearingResponse(
            event_id=row[0],
            congress=row[1],
            chamber=row[2],
            committee_name=row[3],
            hearing_date=row[4],
            hearing_time=row[5],
            title=row[6],
            meeting_type=row[7],
            status=row[8],
            url=row[9],
        )
        for row in rows
    ]

    return HearingsResponse(hearings=hearings, count=total)


@router.get("/api/hearings/stats", response_model=HearingStatsResponse)
def get_hearing_stats(_: None = Depends(RoleChecker(UserRole.VIEWER))):
    """Get hearing summary statistics."""
    con = connect()

    try:
        # Check if hearings table exists
        if not table_exists(con, "hearings"):
            return HearingStatsResponse(
                total_hearings=0, upcoming_count=0, by_committee={}, by_status={}
            )

        today = datetime.now(UTC).strftime("%Y-%m-%d")

        # Total hearings
        cur = execute(con, "SELECT COUNT(*) FROM hearings")
        total_hearings = cur.fetchone()[0]

        # Upcoming count
        cur = execute(
            con,
            "SELECT COUNT(*) FROM hearings WHERE hearing_date >= :today",
            {"today": today},
        )
        upcoming_count = cur.fetchone()[0]

        # By chamber (upcoming only) - group all House VA (full + subcommittees) and Senate VA
        cur = execute(
            con,
            """
            SELECT chamber, COUNT(*) FROM hearings
            WHERE hearing_date >= :today
            GROUP BY chamber
            """,
            {"today": today},
        )
        by_committee = {}
        for row in cur.fetchall():
            chamber = (row[0] or "").lower()
            if chamber == "house":
                by_committee["HVAC"] = row[1]
            elif chamber == "senate":
                by_committee["SVAC"] = row[1]
            else:
                by_committee[chamber] = row[1]

        # By status (upcoming only)
        cur = execute(
            con,
            """
            SELECT status, COUNT(*) FROM hearings
            WHERE hearing_date >= :today
            GROUP BY status
            """,
            {"today": today},
        )
        by_status = dict(cur.fetchall())
    finally:
        con.close()

    return HearingStatsResponse(
        total_hearings=total_hearings,
        upcoming_count=upcoming_count,
        by_committee=by_committee,
        by_status=by_status,
    )
