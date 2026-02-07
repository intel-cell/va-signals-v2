"""
VA Signals Dashboard API

FastAPI backend providing endpoints for monitoring source runs,
document tracking, and system health.
"""

import asyncio
import logging
import os
import sys
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pythonjsonlogger import jsonlogger
from starlette.middleware.base import BaseHTTPMiddleware

from .auth.api import router as auth_router
from .auth.audit import AuditMiddleware
from .auth.middleware import AuthMiddleware
from .battlefield.api import router as battlefield_router
from .ceo_brief.api import router as ceo_brief_router
from .evidence.dashboard_routes import router as evidence_router
from .ml.api import router as ml_router
from .routers.agenda_drift import router as agenda_drift_router
from .routers.compound import router as compound_router
from .routers.health import DeadManResponse, PipelineStaleness  # noqa: F401 - re-exported for tests

# New sub-routers extracted from this file
from .routers.health import router as health_router
from .routers.legislative import router as legislative_router
from .routers.oversight import router as oversight_router
from .routers.pipeline import router as pipeline_router
from .routers.reports import router as reports_router
from .routers.state import router as state_router
from .routers.summaries import router as summaries_router
from .trends.api import router as trends_router
from .websocket import websocket_router

# Prometheus metrics (optional - graceful fallback if not installed)
try:
    from prometheus_fastapi_instrumentator import Instrumentator

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    Instrumentator = None

ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "src" / "dashboard" / "static"

# --- Configuration & Logging ---

# CORS: environment-driven allowed origins (comma-separated)
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get("ALLOWED_ORIGINS", "http://localhost:8000,http://localhost:8080").split(
        ","
    )
    if o.strip()
]

# Configure JSON Logging
logger = logging.getLogger()
logHandler = logging.StreamHandler(sys.stdout)
formatter = jsonlogger.JsonFormatter(
    "%(asctime)s %(levelname)s %(name)s %(message)s",
    rename_fields={"asctime": "timestamp", "levelname": "severity"},
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


# --- FastAPI App ---

app = FastAPI(
    title="VA Signals Dashboard API",
    description="""
## VA Signals & Indicators Intelligence System API

This API provides access to VA regulatory signal tracking, legislative monitoring,
and intelligence aggregation services.

### Authentication
All endpoints require authentication via Firebase or Cloud IAP.
Include the Authorization header with a valid Bearer token.

### Roles
- **viewer**: Read-only access to dashboards and reports
- **analyst**: Access to detailed data and analysis tools
- **leadership**: Access to executive summaries and briefs
- **commander**: Full administrative access

### Rate Limits
API requests are subject to rate limiting. Contact admin for increased limits.

### Support
For API issues, contact: xavier@vetclaims.ai
""",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=[
        {"name": "Health", "description": "System health and status endpoints"},
        {"name": "Runs", "description": "Source run management and statistics"},
        {"name": "Documents", "description": "Federal Register and eCFR document access"},
        {"name": "Bills", "description": "Congressional bill tracking"},
        {"name": "Hearings", "description": "Committee hearing monitoring"},
        {"name": "Oversight", "description": "Oversight monitor events and analysis"},
        {"name": "State", "description": "State-level intelligence signals"},
        {"name": "Agenda Drift", "description": "Member rhetoric deviation detection"},
        {"name": "CEO Briefs", "description": "Executive summary generation"},
        {"name": "Evidence", "description": "Evidence pack assembly"},
        {"name": "Impact", "description": "Impact memos and heat maps"},
        {"name": "Battlefield", "description": "Policy vehicle tracking and calendar"},
        {"name": "Admin", "description": "Administrative functions"},
        {"name": "Audit", "description": "Audit log access"},
        {"name": "WebSocket", "description": "Real-time signal push notifications"},
        {"name": "Metrics", "description": "Prometheus metrics endpoint"},
    ],
)

# Middleware (Applied in reverse order: Last added is first executed)

# 4. Logging (Outermost - measures total time)
app.add_middleware(LoggingMiddleware)

# 3. Audit Logging (Records all API requests for compliance)
app.add_middleware(AuditMiddleware)

# 2. Firebase/Session Auth (Reads cookies + Bearer tokens, sets request.state.auth_context)
app.add_middleware(AuthMiddleware, require_auth=False)

# 1. CORS (Innermost - handles preflight)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
)

# --- Include External Routers ---
app.include_router(battlefield_router)
app.include_router(auth_router)
app.include_router(evidence_router)
app.include_router(ceo_brief_router)
app.include_router(ml_router)

# --- Prometheus Metrics ---
# Exposes /metrics endpoint for Prometheus scraping
if PROMETHEUS_AVAILABLE:
    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_respect_env_var=False,  # Always enable, don't check env var
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/metrics", "/health", "/docs", "/redoc", "/openapi.json"],
        inprogress_name="va_signals_requests_inprogress",
        inprogress_labels=True,
    )

    # Instrument the app
    instrumentator.instrument(app)

    # Expose metrics endpoint - must be done after instrument()
    instrumentator.expose(app, endpoint="/metrics", include_in_schema=True, tags=["Metrics"])

    logger.info("Prometheus metrics enabled at /metrics")
else:
    logger.warning("prometheus-fastapi-instrumentator not installed, /metrics endpoint disabled")

app.include_router(trends_router)
app.include_router(websocket_router)

# --- Include Extracted Sub-Routers ---
app.include_router(health_router)
app.include_router(pipeline_router)
app.include_router(summaries_router)
app.include_router(reports_router)
app.include_router(agenda_drift_router)
app.include_router(legislative_router)
app.include_router(state_router)
app.include_router(oversight_router)
app.include_router(compound_router)

# Mount static files last (catch-all for SPA)
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


# --- Background Tasks ---


async def log_metrics_snapshot():
    """Periodically log system metrics for value tracking."""
    from .routers._helpers import utc_now_iso
    from .routers.oversight import get_oversight_stats_endpoint
    from .routers.pipeline import get_runs_stats
    from .routers.state import get_state_stats_endpoint

    while True:
        try:
            # Collect metrics
            runs_stats = get_runs_stats()
            state_stats = get_state_stats_endpoint()
            oversight_stats = get_oversight_stats_endpoint()

            metrics_data = {
                "event": "metrics_snapshot",
                "timestamp": utc_now_iso(),
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
                },
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
