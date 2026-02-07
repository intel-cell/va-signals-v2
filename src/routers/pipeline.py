"""Pipeline runs, documents, and errors endpoints."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..auth.models import UserRole
from ..auth.rbac import RoleChecker
from ..db import connect, execute
from ._helpers import parse_errors_json

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Runs", "Documents"])


# --- Pydantic Models ---


class SourceRun(BaseModel):
    id: int
    source_id: str
    started_at: str
    ended_at: str
    status: str
    records_fetched: int
    errors: list[str]


class RunsResponse(BaseModel):
    runs: list[SourceRun]
    count: int


class RunsByDay(BaseModel):
    date: str
    count: int


class RunsBySource(BaseModel):
    source_id: str
    count: int


class StatsResponse(BaseModel):
    total_runs: int
    success_count: int
    error_count: int
    no_data_count: int
    success_rate: float
    error_rate: float
    healthy_rate: float  # SUCCESS + NO_DATA (ran without errors)
    runs_today: int
    new_docs_today: int
    runs_by_source: list[RunsBySource]
    runs_by_day: list[RunsByDay]


class FRDocument(BaseModel):
    doc_id: str
    published_date: str
    first_seen_at: str
    source_url: str


class FRDocumentsResponse(BaseModel):
    documents: list[FRDocument]
    count: int


class ECFRDocument(BaseModel):
    doc_id: str
    last_modified: str | None
    etag: str | None
    first_seen_at: str
    source_url: str


class ECFRDocumentsResponse(BaseModel):
    documents: list[ECFRDocument]
    count: int


class ErrorRun(BaseModel):
    id: int
    source_id: str
    ended_at: str
    status: str
    errors: list[str]


class ErrorsResponse(BaseModel):
    error_runs: list[ErrorRun]
    count: int


# --- Endpoints ---


@router.get("/api/runs", response_model=RunsResponse)
def get_runs(
    source_id: str | None = Query(None, description="Filter by source ID"),
    status: str | None = Query(None, description="Filter by status (SUCCESS, NO_DATA, ERROR)"),
    limit: int = Query(50, ge=1, le=500, description="Number of runs to return"),
    _: None = Depends(RoleChecker(UserRole.ANALYST)),
):
    """Get recent source runs with optional filters. Requires ANALYST role."""
    con = connect()

    query = "SELECT id, source_id, started_at, ended_at, status, records_fetched, errors_json FROM source_runs WHERE 1=1"
    params: dict[str, Any] = {}

    if source_id:
        query += " AND source_id = :source_id"
        params["source_id"] = source_id
    if status:
        query += " AND status = :status"
        params["status"] = status

    query += " ORDER BY ended_at DESC LIMIT :limit"
    params["limit"] = limit

    cur = execute(con, query, params)
    rows = cur.fetchall()
    con.close()

    runs = [
        SourceRun(
            id=row[0],
            source_id=row[1],
            started_at=row[2],
            ended_at=row[3],
            status=row[4],
            records_fetched=row[5],
            errors=parse_errors_json(row[6]),
        )
        for row in rows
    ]

    return RunsResponse(runs=runs, count=len(runs))


@router.get("/api/runs/stats", response_model=StatsResponse)
def get_runs_stats(_: None = Depends(RoleChecker(UserRole.VIEWER))):
    """Get aggregated statistics for source runs. Requires VIEWER role."""
    con = connect()

    # Total counts by status
    cur = execute(con, "SELECT status, COUNT(*) FROM source_runs GROUP BY status")
    status_counts = dict(cur.fetchall())

    total_runs = sum(status_counts.values())
    success_count = status_counts.get("SUCCESS", 0)
    error_count = status_counts.get("ERROR", 0)
    no_data_count = status_counts.get("NO_DATA", 0)

    success_rate = (success_count / total_runs * 100) if total_runs > 0 else 0.0
    error_rate = (error_count / total_runs * 100) if total_runs > 0 else 0.0
    healthy_rate = ((success_count + no_data_count) / total_runs * 100) if total_runs > 0 else 0.0

    # Runs by source
    cur = execute(
        con,
        "SELECT source_id, COUNT(*) FROM source_runs GROUP BY source_id ORDER BY COUNT(*) DESC",
    )
    runs_by_source = [RunsBySource(source_id=row[0], count=row[1]) for row in cur.fetchall()]

    # Runs by day (last 7 days)
    seven_days_ago = (datetime.now(UTC) - timedelta(days=7)).strftime("%Y-%m-%d")
    cur = execute(
        con,
        """
        SELECT DATE(ended_at) as day, COUNT(*)
        FROM source_runs
        WHERE DATE(ended_at) >= :seven_days_ago
        GROUP BY day
        ORDER BY day DESC
        """,
        {"seven_days_ago": seven_days_ago},
    )
    runs_by_day = [RunsByDay(date=row[0], count=row[1]) for row in cur.fetchall()]

    # Runs in last 24 hours
    twenty_four_hours_ago = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
    cur = execute(
        con,
        "SELECT COUNT(*) FROM source_runs WHERE ended_at >= :since",
        {"since": twenty_four_hours_ago},
    )
    runs_today = cur.fetchone()[0]

    # New docs in last 24 hours
    cur = execute(
        con,
        "SELECT COUNT(*) FROM fr_seen WHERE first_seen_at >= :since",
        {"since": twenty_four_hours_ago},
    )
    new_docs_today = cur.fetchone()[0]

    con.close()

    return StatsResponse(
        total_runs=total_runs,
        success_count=success_count,
        error_count=error_count,
        no_data_count=no_data_count,
        success_rate=round(success_rate, 2),
        error_rate=round(error_rate, 2),
        healthy_rate=round(healthy_rate, 2),
        runs_today=runs_today,
        new_docs_today=new_docs_today,
        runs_by_source=runs_by_source,
        runs_by_day=runs_by_day,
    )


@router.get("/api/documents/fr", response_model=FRDocumentsResponse)
def get_fr_documents(
    limit: int = Query(100, ge=1, le=1000, description="Number of documents to return"),
    _: None = Depends(RoleChecker(UserRole.ANALYST)),
):
    """Get recent Federal Register documents. Requires ANALYST role."""
    con = connect()
    cur = execute(
        con,
        """
        SELECT doc_id, published_date, first_seen_at, source_url
        FROM fr_seen
        ORDER BY first_seen_at DESC
        LIMIT :limit
        """,
        {"limit": limit},
    )
    rows = cur.fetchall()

    # Get total count
    cur = execute(con, "SELECT COUNT(*) FROM fr_seen")
    total_count = cur.fetchone()[0]

    con.close()

    documents = [
        FRDocument(
            doc_id=row[0],
            published_date=row[1],
            first_seen_at=row[2],
            source_url=row[3],
        )
        for row in rows
    ]

    return FRDocumentsResponse(documents=documents, count=total_count)


@router.get("/api/documents/ecfr", response_model=ECFRDocumentsResponse)
def get_ecfr_documents(_: None = Depends(RoleChecker(UserRole.ANALYST))):
    """Get eCFR tracking status. Requires ANALYST role."""
    con = connect()
    cur = execute(
        con,
        """
        SELECT doc_id, last_modified, etag, first_seen_at, source_url
        FROM ecfr_seen
        ORDER BY first_seen_at DESC
        """,
    )
    rows = cur.fetchall()
    con.close()

    documents = [
        ECFRDocument(
            doc_id=row[0],
            last_modified=row[1],
            etag=row[2],
            first_seen_at=row[3],
            source_url=row[4],
        )
        for row in rows
    ]

    return ECFRDocumentsResponse(documents=documents, count=len(documents))


@router.get("/api/errors", response_model=ErrorsResponse)
def get_errors(
    limit: int = Query(20, ge=1, le=100, description="Number of error runs to return"),
    _: None = Depends(RoleChecker(UserRole.ANALYST)),
):
    """Get recent runs with errors. Requires ANALYST role."""
    con = connect()
    cur = execute(
        con,
        """
        SELECT id, source_id, ended_at, status, errors_json
        FROM source_runs
        WHERE status = 'ERROR' OR errors_json != '[]'
        ORDER BY ended_at DESC
        LIMIT :limit
        """,
        {"limit": limit},
    )
    rows = cur.fetchall()
    con.close()

    error_runs = [
        ErrorRun(
            id=row[0],
            source_id=row[1],
            ended_at=row[2],
            status=row[3],
            errors=parse_errors_json(row[4]),
        )
        for row in rows
        if parse_errors_json(row[4])  # Only include if there are actual errors
    ]

    return ErrorsResponse(error_runs=error_runs, count=len(error_runs))
