"""
VA Signals Dashboard API

FastAPI backend providing endpoints for monitoring source runs,
document tracking, and system health.
"""

import json
import os
import secrets
import asyncio
import time
import logging
import sys
import base64
import binascii
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, Query, HTTPException, Request, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
from pythonjsonlogger import jsonlogger

from .db import connect, execute, table_exists
from .reports import generate_report
from .state.db_helpers import (
    get_signals_by_state,
    get_recent_runs,
    get_signal_count_by_state,
    get_signal_count_by_severity,
    get_latest_run,
)
from .oversight.db_helpers import get_oversight_stats, get_oversight_events
from .battlefield.api import router as battlefield_router
from .auth.api import router as auth_router

ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "src" / "dashboard" / "static"

# --- Configuration & Logging ---

# Basic Auth Config
AUTH_USERNAME = os.environ.get("AUTH_USERNAME", "admin")
AUTH_PASSWORD = os.environ.get("AUTH_PASSWORD", "secret")

# Configure JSON Logging
logger = logging.getLogger()
logHandler = logging.StreamHandler(sys.stdout)
formatter = jsonlogger.JsonFormatter(
    "%(asctime)s %(levelname)s %(name)s %(message)s",
    rename_fields={"asctime": "timestamp", "levelname": "severity"}
)
logHandler.setFormatter(formatter)
logger.addHandler(logHandler)
logger.setLevel(logging.INFO)

# --- Middleware ---

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = (time.time() - start_time) * 1000
        
        log_data = {
            "event": "access_log",
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "processing_time_ms": round(process_time, 2),
            "user_agent": request.headers.get("user-agent"),
            "client_ip": request.client.host if request.client else None,
        }
        
        # Add user if authenticated
        if hasattr(request.state, "user"):
            log_data["user"] = request.state.user
            
        logger.info("request_processed", extra=log_data)
        return response

class BasicAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Allow health checks if we had them, but protecting all for now.
        
        if "Authorization" not in request.headers:
            return Response(
                status_code=401,
                headers={"WWW-Authenticate": "Basic"},
                content="Unauthorized"
            )
            
        auth = request.headers["Authorization"]
        try:
            scheme, credentials = auth.split()
            if scheme.lower() != 'basic':
                raise ValueError
            decoded = base64.b64decode(credentials).decode("ascii")
            username, _, password = decoded.partition(":")
            
            # Constant time comparison
            is_correct_username = secrets.compare_digest(username, AUTH_USERNAME)
            is_correct_password = secrets.compare_digest(password, AUTH_PASSWORD)
            
            if not (is_correct_username and is_correct_password):
                 return Response(
                    status_code=401,
                    headers={"WWW-Authenticate": "Basic"},
                    content="Invalid credentials"
                )
                
            request.state.user = username
            
        except (ValueError, UnicodeDecodeError, binascii.Error):
            return Response(
                status_code=401,
                headers={"WWW-Authenticate": "Basic"},
                content="Invalid authentication header"
            )
            
        return await call_next(request)

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
    last_modified: Optional[str]
    etag: Optional[str]
    first_seen_at: str
    source_url: str


class ECFRDocumentsResponse(BaseModel):
    documents: list[ECFRDocument]
    count: int


class SourceHealth(BaseModel):
    source_id: str
    last_success_at: Optional[str]
    hours_since_success: Optional[float]
    last_run_status: Optional[str]


class HealthResponse(BaseModel):
    sources: list[SourceHealth]
    checked_at: str


class ErrorRun(BaseModel):
    id: int
    source_id: str
    ended_at: str
    status: str
    errors: list[str]


class ErrorsResponse(BaseModel):
    error_runs: list[ErrorRun]
    count: int


class FRSummary(BaseModel):
    doc_id: str
    summary: str
    bullet_points: list[str]
    veteran_impact: str
    tags: list[str]
    summarized_at: str
    source_url: Optional[str] = None


class SummariesResponse(BaseModel):
    summaries: list[FRSummary]
    count: int


class ReportResponse(BaseModel):
    report_type: str
    generated_at: str
    period: dict
    summary: dict
    runs: list[dict]
    new_documents: list[dict]


class ADDeviationEvent(BaseModel):
    id: int
    member_id: str
    member_name: str
    hearing_id: str
    utterance_id: str
    cos_dist: float
    zscore: float
    detected_at: str
    note: Optional[str]


class ADDeviationResponse(BaseModel):
    events: list[ADDeviationEvent]
    count: int


class ADMemberStats(BaseModel):
    member_id: str
    name: str
    event_count: int
    avg_zscore: float


class BillResponse(BaseModel):
    bill_id: str
    congress: int
    bill_type: str
    bill_number: int
    title: str
    sponsor_name: Optional[str]
    sponsor_party: Optional[str]
    sponsor_state: Optional[str]
    latest_action_date: Optional[str]
    latest_action_text: Optional[str]
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
    committee_name: Optional[str]
    hearing_date: str
    hearing_time: Optional[str]
    title: Optional[str]
    meeting_type: Optional[str]
    status: str
    url: Optional[str]


class HearingsResponse(BaseModel):
    hearings: list[HearingResponse]
    count: int


class HearingStatsResponse(BaseModel):
    total_hearings: int
    upcoming_count: int
    by_committee: dict[str, int]
    by_status: dict[str, int]


# --- State Intelligence Models ---

class StateSignal(BaseModel):
    signal_id: str
    state: str
    title: str
    url: str
    severity: Optional[str] = None
    program: Optional[str] = None
    pub_date: Optional[str] = None


class StateSignalsResponse(BaseModel):
    signals: list[StateSignal]
    count: int


class StateRun(BaseModel):
    id: int
    run_type: str
    state: Optional[str] = None
    status: str
    signals_found: int
    high_severity_count: int
    started_at: str
    finished_at: Optional[str] = None


class StateRunsResponse(BaseModel):
    runs: list[StateRun]
    count: int


class StateStatsResponse(BaseModel):
    total_signals: int
    by_state: dict[str, int]
    by_severity: dict[str, int]
    last_run: Optional[dict] = None


# --- Oversight Monitor Models ---

class OversightEvent(BaseModel):
    event_id: str
    title: str
    primary_source_type: str
    primary_url: str
    pub_timestamp: Optional[str]
    is_escalation: bool
    is_deviation: bool
    surfaced: bool
    surfaced_at: Optional[str]
    fetched_at: str


class OversightEventsResponse(BaseModel):
    events: list[OversightEvent]
    count: int


class OversightStatsResponse(BaseModel):
    total_events: int
    escalations: int
    deviations: int
    surfaced: int
    last_event_at: Optional[str]
    by_source: dict[str, int]

# --- FastAPI App ---

app = FastAPI(
    title="VA Signals Dashboard API",
    description="Monitoring API for VA regulatory signal tracking",
    version="1.0.0",
)

# Middleware (Applied in reverse order: Last added is first executed)

# 3. Logging (Outermost - measures total time)
app.add_middleware(LoggingMiddleware)

# 2. Basic Auth - DISABLED (Cloud Run IAM handles authentication)
# app.add_middleware(BasicAuthMiddleware)

# 1. CORS (Innermost - handles preflight)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include battlefield dashboard router
app.include_router(battlefield_router)

# Include authentication router
app.include_router(auth_router)


def _parse_errors_json(errors_json: str) -> list[str]:
    """Parse errors_json column, handling malformed data gracefully."""
    try:
        errors = json.loads(errors_json) if errors_json else []
        return errors if isinstance(errors, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- Endpoints ---

@app.get("/api/runs", response_model=RunsResponse)
def get_runs(
    source_id: Optional[str] = Query(None, description="Filter by source ID"),
    status: Optional[str] = Query(None, description="Filter by status (SUCCESS, NO_DATA, ERROR)"),
    limit: int = Query(50, ge=1, le=500, description="Number of runs to return"),
):
    """Get recent source runs with optional filters."""
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
            errors=_parse_errors_json(row[6]),
        )
        for row in rows
    ]

    return RunsResponse(runs=runs, count=len(runs))


@app.get("/api/runs/stats", response_model=StatsResponse)
def get_runs_stats():
    """Get aggregated statistics for source runs."""
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
    seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
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
    twenty_four_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
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


@app.get("/api/documents/fr", response_model=FRDocumentsResponse)
def get_fr_documents(
    limit: int = Query(100, ge=1, le=1000, description="Number of documents to return"),
):
    """Get recent Federal Register documents."""
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


@app.get("/api/documents/ecfr", response_model=ECFRDocumentsResponse)
def get_ecfr_documents():
    """Get eCFR tracking status."""
    con = connect()
    cur = execute(
        con,
        """
        SELECT doc_id, last_modified, etag, first_seen_at, source_url
        FROM ecfr_seen
        ORDER BY first_seen_at DESC
        """
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


@app.get("/api/health", response_model=HealthResponse)
def get_health():
    """Get health status for each source: last successful run and time since."""
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

    return HealthResponse(sources=sources, checked_at=_utc_now_iso())


@app.get("/api/errors", response_model=ErrorsResponse)
def get_errors(
    limit: int = Query(20, ge=1, le=100, description="Number of error runs to return"),
):
    """Get recent runs with errors."""
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
            errors=_parse_errors_json(row[4]),
        )
        for row in rows
        if _parse_errors_json(row[4])  # Only include if there are actual errors
    ]

    return ErrorsResponse(error_runs=error_runs, count=len(error_runs))


@app.get("/api/summaries", response_model=SummariesResponse)
def get_summaries(
    limit: int = Query(50, ge=1, le=200, description="Number of summaries to return"),
):
    """Get recent document summaries with source URLs."""
    con = connect()
    # Check if fr_summaries table exists
    if not table_exists(con, "fr_summaries"):
        con.close()
        return SummariesResponse(summaries=[], count=0)

    # Join with fr_seen to get source_url
    cur = execute(
        con,
        """
        SELECT s.doc_id, s.summary, s.bullet_points, s.veteran_impact, s.tags,
               s.summarized_at, f.source_url
        FROM fr_summaries s
        LEFT JOIN fr_seen f ON s.doc_id = f.doc_id
        ORDER BY s.summarized_at DESC
        LIMIT :limit
        """,
        {"limit": limit},
    )
    rows = cur.fetchall()
    con.close()

    summaries = []
    for row in rows:
        doc_id, summary, bullet_points_json, veteran_impact, tags_json, summarized_at, source_url = row
        try:
            bullet_points = json.loads(bullet_points_json) if bullet_points_json else []
        except (json.JSONDecodeError, TypeError):
            bullet_points = []
        try:
            tags = json.loads(tags_json) if tags_json else []
        except (json.JSONDecodeError, TypeError):
            tags = []

        summaries.append(
            FRSummary(
                doc_id=doc_id,
                summary=summary or "",
                bullet_points=bullet_points,
                veteran_impact=veteran_impact or "",
                tags=tags,
                summarized_at=summarized_at or "",
                source_url=source_url,
            )
        )

    return SummariesResponse(summaries=summaries, count=len(summaries))


@app.get("/api/summaries/{doc_id}", response_model=FRSummary)
def get_summary(doc_id: str):
    """Get a specific document summary by doc_id."""
    con = connect()
    # Check if fr_summaries table exists
    if not table_exists(con, "fr_summaries"):
        con.close()
        raise HTTPException(status_code=404, detail="Summary not found")

    cur = execute(
        con,
        """
        SELECT s.doc_id, s.summary, s.bullet_points, s.veteran_impact, s.tags,
               s.summarized_at, f.source_url
        FROM fr_summaries s
        LEFT JOIN fr_seen f ON s.doc_id = f.doc_id
        WHERE s.doc_id = :doc_id
        """,
        {"doc_id": doc_id},
    )
    row = cur.fetchone()
    con.close()

    if not row:
        raise HTTPException(status_code=404, detail="Summary not found")

    doc_id, summary, bullet_points_json, veteran_impact, tags_json, summarized_at, source_url = row
    try:
        bullet_points = json.loads(bullet_points_json) if bullet_points_json else []
    except (json.JSONDecodeError, TypeError):
        bullet_points = []
    try:
        tags = json.loads(tags_json) if tags_json else []
    except (json.JSONDecodeError, TypeError):
        tags = []

    return FRSummary(
        doc_id=doc_id,
        summary=summary or "",
        bullet_points=bullet_points,
        veteran_impact=veteran_impact or "",
        tags=tags,
        summarized_at=summarized_at or "",
        source_url=source_url,
    )


@app.get("/api/summaries/check/{doc_id}")
def check_summary_exists(doc_id: str):
    """Check if a summary exists for a given doc_id."""
    con = connect()
    # Check if fr_summaries table exists
    if not table_exists(con, "fr_summaries"):
        con.close()
        return {"exists": False}

    cur = execute(
        con,
        "SELECT 1 FROM fr_summaries WHERE doc_id = :doc_id",
        {"doc_id": doc_id},
    )
    exists = cur.fetchone() is not None
    con.close()

    return {"exists": exists}


@app.get("/api/summaries/doc-ids")
def get_summarized_doc_ids():
    """Get list of all doc_ids that have summaries."""
    con = connect()
    # Check if fr_summaries table exists
    if not table_exists(con, "fr_summaries"):
        con.close()
        return {"doc_ids": []}

    cur = execute(con, "SELECT doc_id FROM fr_summaries")
    doc_ids = [row[0] for row in cur.fetchall()]
    con.close()

    return {"doc_ids": doc_ids}


@app.get("/api/reports/generate")
def generate_report_endpoint(
    type: str = Query("daily", description="Report type: daily or weekly"),
    format: str = Query("json", description="Output format: json"),
):
    """Generate and return a report."""
    if type not in ("daily", "weekly"):
        raise HTTPException(
            status_code=400, detail="Invalid report type. Use 'daily' or 'weekly'"
        )

    if format != "json":
        raise HTTPException(
            status_code=400, detail="Only 'json' format is supported"
        )

    try:
        report = generate_report(type)
        return JSONResponse(content=report)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating report: {str(e)}")


# --- Agenda Drift Endpoints ---

@app.get("/api/agenda-drift/events", response_model=ADDeviationResponse)
def get_ad_events(
    limit: int = Query(50, ge=1, le=500, description="Number of events to return"),
    min_zscore: float = Query(2.0, description="Minimum z-score filter"),
):
    """Get recent agenda drift deviation events."""
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


@app.get("/api/agenda-drift/stats")
def get_ad_stats():
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
            "checked_at": _utc_now_iso()
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
           ORDER BY event_count DESC"""
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
        "checked_at": _utc_now_iso()
    }


@app.get("/api/agenda-drift/members/{member_id}/history")
def get_ad_member_history(
    member_id: str,
    limit: int = Query(20, ge=1, le=100, description="Number of events to return"),
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


# --- Bills Endpoints ---

@app.get("/api/bills", response_model=BillsResponse)
def get_bills(
    limit: int = Query(50, ge=1, le=500, description="Number of bills to return"),
    congress: Optional[int] = Query(None, description="Filter by congress number"),
):
    """List tracked VA bills."""
    con = connect()

    # Check if bills table exists
    if not table_exists(con, "bills"):
        con.close()
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


@app.get("/api/bills/stats", response_model=BillStatsResponse)
def get_bill_stats():
    """Get bill summary statistics."""
    con = connect()

    # Check if bills table exists
    if not table_exists(con, "bills"):
        con.close()
        return BillStatsResponse(total_bills=0, new_this_week=0, by_type={}, by_congress={})

    # Total bills
    cur = execute(con, "SELECT COUNT(*) FROM bills")
    total_bills = cur.fetchone()[0]

    # New this week
    seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
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
    cur = execute(con, "SELECT congress, COUNT(*) FROM bills GROUP BY congress ORDER BY congress DESC")
    by_congress = {int(row[0]): row[1] for row in cur.fetchall()}

    con.close()

    return BillStatsResponse(
        total_bills=total_bills,
        new_this_week=new_this_week,
        by_type=by_type,
        by_congress=by_congress,
    )


# --- Hearings Endpoints ---

@app.get("/api/hearings", response_model=HearingsResponse)
def get_hearings(
    upcoming: bool = Query(True, description="Show only upcoming hearings"),
    limit: int = Query(20, ge=1, le=100, description="Number of hearings to return"),
):
    """List hearings - default to upcoming only."""
    con = connect()

    # Check if hearings table exists
    if not table_exists(con, "hearings"):
        con.close()
        return HearingsResponse(hearings=[], count=0)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

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


@app.get("/api/hearings/stats", response_model=HearingStatsResponse)
def get_hearing_stats():
    """Get hearing summary statistics."""
    con = connect()

    # Check if hearings table exists
    if not table_exists(con, "hearings"):
        con.close()
        return HearingStatsResponse(
            total_hearings=0, upcoming_count=0, by_committee={}, by_status={}
        )

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

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

    con.close()

    return HearingStatsResponse(
        total_hearings=total_hearings,
        upcoming_count=upcoming_count,
        by_committee=by_committee,
        by_status=by_status,
    )


# --- State Intelligence Endpoints ---


@app.get("/api/state/signals", response_model=StateSignalsResponse)
def get_state_signals_endpoint(
    state: Optional[str] = Query(None, description="Filter by state code (TX, CA, FL)"),
    severity: Optional[str] = Query(None, description="Filter by severity (high, medium, low)"),
    limit: int = Query(50, ge=1, le=500, description="Max signals to return"),
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


@app.get("/api/state/runs", response_model=StateRunsResponse)
def get_state_runs_endpoint(
    limit: int = Query(20, ge=1, le=500, description="Max runs to return"),
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


@app.get("/api/state/stats", response_model=StateStatsResponse)
def get_state_stats_endpoint():
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


# --- Oversight Monitor Endpoints ---

@app.get("/api/oversight/stats", response_model=OversightStatsResponse)
def get_oversight_stats_endpoint():
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


@app.get("/api/oversight/events", response_model=OversightEventsResponse)
def get_oversight_events_endpoint(
    limit: int = Query(50, ge=1, le=500, description="Max events to return"),
    source_type: Optional[str] = Query(None, description="Filter by source type"),
    escalations_only: bool = Query(False, description="Only escalation events"),
    deviations_only: bool = Query(False, description="Only deviation events"),
    surfaced_only: bool = Query(False, description="Only surfaced events"),
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

# Mount static files last (catch-all for SPA)
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


# --- Background Tasks ---

async def log_metrics_snapshot():
    """Periodically log system metrics for value tracking."""
    while True:
        try:
            # Wait for 1 hour (3600 seconds)
            # We wait first to avoid double-logging on startup (if we want)
            # But usually we want one on startup. Let's wait at the end.
            
            # Collect metrics
            runs_stats = get_runs_stats()
            state_stats = get_state_stats_endpoint()
            oversight_stats = get_oversight_stats_endpoint()
            
            metrics_data = {
                "event": "metrics_snapshot",
                "timestamp": _utc_now_iso(),
                "federal": {
                    "total_runs": runs_stats.total_runs,
                    "success_rate": runs_stats.success_rate,
                    "runs_today": runs_stats.runs_today,
                    "new_docs_today": runs_stats.new_docs_today,
                },
                "state": {
                    "total_signals": state_stats.total_signals,
                    "high_severity": state_stats.by_severity.get("high", 0),
                    "states_covered": len(state_stats.by_state),
                },
                "oversight": {
                    "total_events": oversight_stats.total_events,
                    "escalations": oversight_stats.escalations,
                    "deviations": oversight_stats.deviations,
                }
            }
            
            logger.info("metrics_snapshot", extra=metrics_data)
            
        except Exception as e:
            logger.error(f"Error in metrics snapshot: {str(e)}")
            
        await asyncio.sleep(3600)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(log_metrics_snapshot())


# --- Main entry point ---

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
