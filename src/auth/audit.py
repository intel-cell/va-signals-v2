"""
Audit Logging Module

Provides:
- Comprehensive request/response logging
- Async logging to avoid request delays
- Audit trail for compliance
- Query interface for audit records
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Any
from queue import Queue
from threading import Thread

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from .models import AuthContext

logger = logging.getLogger(__name__)

# Async queue for audit logs
_audit_queue: Queue = Queue()
_audit_worker_started = False


# --- Audit Log Entry ---

def _generate_log_id() -> str:
    """Generate unique audit log ID."""
    return f"AUDIT_{datetime.now(timezone.utc).strftime('%Y%m%d')}_{uuid.uuid4().hex[:12]}"


def _sanitize_body(body: Optional[str], max_length: int = 10000) -> Optional[str]:
    """Sanitize request body, removing sensitive fields and truncating."""
    if not body:
        return None

    try:
        data = json.loads(body)

        # Remove sensitive fields
        sensitive_fields = {"password", "token", "secret", "api_key", "authorization"}
        for field in sensitive_fields:
            if field in data:
                data[field] = "[REDACTED]"

        sanitized = json.dumps(data)
        if len(sanitized) > max_length:
            return sanitized[:max_length] + "...[TRUNCATED]"
        return sanitized

    except (json.JSONDecodeError, TypeError):
        # Not JSON, return truncated string
        if len(body) > max_length:
            return body[:max_length] + "...[TRUNCATED]"
        return body


# --- Async Audit Worker ---

def _audit_worker():
    """Background worker that writes audit logs to database."""
    from ..db import connect, execute

    while True:
        try:
            # Block until we get an entry
            entry = _audit_queue.get()

            if entry is None:
                # Shutdown signal
                break

            con = connect()
            execute(
                con,
                """INSERT INTO audit_log (
                    log_id, timestamp, user_id, user_email, action,
                    resource, resource_id, request_method, request_path,
                    request_body, response_status, ip_address, user_agent,
                    duration_ms, success
                ) VALUES (
                    :log_id, :timestamp, :user_id, :user_email, :action,
                    :resource, :resource_id, :request_method, :request_path,
                    :request_body, :response_status, :ip_address, :user_agent,
                    :duration_ms, :success
                )""",
                entry
            )
            con.commit()
            con.close()

            _audit_queue.task_done()

        except Exception as e:
            logger.error(f"Audit worker error: {e}")


def _start_audit_worker():
    """Start the background audit worker if not already running."""
    global _audit_worker_started

    if not _audit_worker_started:
        worker = Thread(target=_audit_worker, daemon=True)
        worker.start()
        _audit_worker_started = True
        logger.info("Audit worker started")


def log_audit(
    user_id: Optional[str],
    user_email: Optional[str],
    action: str,
    resource: Optional[str] = None,
    resource_id: Optional[str] = None,
    request_method: Optional[str] = None,
    request_path: Optional[str] = None,
    request_body: Optional[str] = None,
    response_status: Optional[int] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    duration_ms: Optional[int] = None,
    success: bool = True,
):
    """
    Queue an audit log entry for async writing.

    This function is non-blocking and returns immediately.
    """
    _start_audit_worker()

    entry = {
        "log_id": _generate_log_id(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "user_email": user_email,
        "action": action,
        "resource": resource,
        "resource_id": resource_id,
        "request_method": request_method,
        "request_path": request_path,
        "request_body": _sanitize_body(request_body),
        "response_status": response_status,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "duration_ms": duration_ms,
        "success": success,
    }

    _audit_queue.put(entry)


# --- Audit Middleware ---

class AuditMiddleware(BaseHTTPMiddleware):
    """
    Middleware that logs all API requests for audit compliance.

    Captures:
    - Request method, path, body
    - User identity (from auth context)
    - Response status code
    - Request duration
    - Client IP and user agent
    """

    # Paths to skip auditing (health checks, static files, etc.)
    SKIP_PATHS = {
        "/health",
        "/",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/favicon.ico",
    }

    SKIP_PREFIXES = [
        "/static",
        "/_next",
    ]

    def __init__(self, app, log_request_body: bool = True):
        super().__init__(app)
        self.log_request_body = log_request_body
        _start_audit_worker()

    async def dispatch(self, request: Request, call_next):
        # Skip certain paths
        path = request.url.path
        if path in self.SKIP_PATHS:
            return await call_next(request)

        for prefix in self.SKIP_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        # Start timing
        start_time = time.time()

        # Capture request body for POST/PUT/PATCH
        request_body = None
        if self.log_request_body and request.method in ("POST", "PUT", "PATCH"):
            try:
                body_bytes = await request.body()
                request_body = body_bytes.decode("utf-8") if body_bytes else None
            except Exception:
                request_body = "[BODY_READ_ERROR]"

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)

        # Get user context if available
        auth_context: Optional[AuthContext] = getattr(request.state, "auth_context", None)
        user_id = auth_context.user_id if auth_context else None
        user_email = auth_context.email if auth_context else None

        # Determine action from method and path
        action = self._determine_action(request.method, path)

        # Extract resource info
        resource, resource_id = self._extract_resource(path)

        # Get client info
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")

        # Log the audit entry
        log_audit(
            user_id=user_id,
            user_email=user_email,
            action=action,
            resource=resource,
            resource_id=resource_id,
            request_method=request.method,
            request_path=path,
            request_body=request_body,
            response_status=response.status_code,
            ip_address=ip_address,
            user_agent=user_agent,
            duration_ms=duration_ms,
            success=200 <= response.status_code < 400,
        )

        return response

    def _determine_action(self, method: str, path: str) -> str:
        """Determine action name from method and path."""
        # Map common patterns
        if "/login" in path:
            return "auth:login"
        if "/logout" in path:
            return "auth:logout"
        if "/users" in path:
            if method == "POST":
                return "user:create"
            if method == "PATCH":
                return "user:update"
            if method == "DELETE":
                return "user:delete"
            return "user:read"

        # Generic action from method
        method_actions = {
            "GET": "read",
            "POST": "create",
            "PUT": "update",
            "PATCH": "update",
            "DELETE": "delete",
        }
        return f"api:{method_actions.get(method, method.lower())}"

    def _extract_resource(self, path: str) -> tuple[Optional[str], Optional[str]]:
        """Extract resource type and ID from path."""
        # Remove /api/ prefix
        clean_path = path.lstrip("/api/").lstrip("/")
        parts = clean_path.split("/")

        if not parts:
            return None, None

        resource = parts[0]
        resource_id = parts[1] if len(parts) > 1 else None

        return resource, resource_id


# --- Query Functions ---

def get_audit_logs(
    user_id: Optional[str] = None,
    user_email: Optional[str] = None,
    action: Optional[str] = None,
    resource: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    success_only: Optional[bool] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """
    Query audit logs with filters.

    Returns list of audit log entries matching filters.
    """
    from ..db import connect, execute

    query = "SELECT * FROM audit_log WHERE 1=1"
    params: dict[str, Any] = {}

    if user_id:
        query += " AND user_id = :user_id"
        params["user_id"] = user_id

    if user_email:
        query += " AND user_email = :user_email"
        params["user_email"] = user_email

    if action:
        query += " AND action LIKE :action"
        params["action"] = f"%{action}%"

    if resource:
        query += " AND resource = :resource"
        params["resource"] = resource

    if start_date:
        query += " AND timestamp >= :start_date"
        params["start_date"] = start_date.isoformat()

    if end_date:
        query += " AND timestamp <= :end_date"
        params["end_date"] = end_date.isoformat()

    if success_only is not None:
        query += " AND success = :success"
        params["success"] = success_only

    query += " ORDER BY timestamp DESC LIMIT :limit OFFSET :offset"
    params["limit"] = limit
    params["offset"] = offset

    con = connect()
    cur = execute(con, query, params)
    columns = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    con.close()

    return [dict(zip(columns, row)) for row in rows]


def get_audit_stats(days: int = 7) -> dict:
    """
    Get audit statistics for the specified period.

    Returns summary stats including:
    - Total requests
    - Requests by action
    - Requests by user
    - Error rate
    - Average duration
    """
    from ..db import connect, execute

    start_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    con = connect()

    # Total requests
    cur = execute(
        con,
        "SELECT COUNT(*) FROM audit_log WHERE timestamp >= :start_date",
        {"start_date": start_date}
    )
    total_requests = cur.fetchone()[0]

    # Requests by action
    cur = execute(
        con,
        """SELECT action, COUNT(*) as count
           FROM audit_log
           WHERE timestamp >= :start_date
           GROUP BY action
           ORDER BY count DESC
           LIMIT 20""",
        {"start_date": start_date}
    )
    by_action = {row[0]: row[1] for row in cur.fetchall()}

    # Requests by user
    cur = execute(
        con,
        """SELECT user_email, COUNT(*) as count
           FROM audit_log
           WHERE timestamp >= :start_date AND user_email IS NOT NULL
           GROUP BY user_email
           ORDER BY count DESC
           LIMIT 10""",
        {"start_date": start_date}
    )
    by_user = {row[0]: row[1] for row in cur.fetchall()}

    # Error rate
    cur = execute(
        con,
        """SELECT
             SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as errors,
             COUNT(*) as total
           FROM audit_log
           WHERE timestamp >= :start_date""",
        {"start_date": start_date}
    )
    row = cur.fetchone()
    errors = row[0] or 0
    total = row[1] or 1
    error_rate = (errors / total) * 100

    # Average duration
    cur = execute(
        con,
        """SELECT AVG(duration_ms)
           FROM audit_log
           WHERE timestamp >= :start_date AND duration_ms IS NOT NULL""",
        {"start_date": start_date}
    )
    avg_duration = cur.fetchone()[0] or 0

    con.close()

    return {
        "period_days": days,
        "total_requests": total_requests,
        "by_action": by_action,
        "by_user": by_user,
        "error_count": errors,
        "error_rate_percent": round(error_rate, 2),
        "avg_duration_ms": round(avg_duration, 2),
    }


def export_audit_logs_csv(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> str:
    """
    Export audit logs to CSV format.

    Returns CSV string.
    """
    import csv
    import io

    logs = get_audit_logs(
        start_date=start_date,
        end_date=end_date,
        limit=10000,
    )

    if not logs:
        return "No audit logs found for the specified period."

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=logs[0].keys())
    writer.writeheader()
    writer.writerows(logs)

    return output.getvalue()


# --- Cleanup ---

def shutdown_audit_worker():
    """Gracefully shutdown the audit worker."""
    _audit_queue.put(None)
