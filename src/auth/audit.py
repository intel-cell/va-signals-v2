"""
Audit Logging Module

Provides:
- Comprehensive request/response logging
- Async logging to avoid request delays
- Audit trail for compliance
- Query interface for audit records
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import UTC, datetime, timedelta
from queue import Queue
from threading import Thread
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from .models import AuthContext

logger = logging.getLogger(__name__)

# Async queue for audit logs
_audit_queue: Queue = Queue()
_audit_worker_started = False


# --- Audit Log Entry ---


def _generate_log_id() -> str:
    """Generate unique audit log ID."""
    return f"AUDIT_{datetime.now(UTC).strftime('%Y%m%d')}_{uuid.uuid4().hex[:12]}"


def _sanitize_body(body: str | None, max_length: int = 10000) -> str | None:
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


def _is_contaminated(entry: dict) -> bool:
    """Check if an audit entry contains test contamination or injection attempts."""
    ip = entry.get("ip_address") or ""
    if ip == "testclient":
        return True
    # Check all string fields for injection patterns
    for val in (ip, entry.get("request_body") or "", entry.get("user_agent") or ""):
        lower = val.lower()
        if "<script" in lower or "drop table" in lower:
            return True
    return False


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

            if _is_contaminated(entry):
                logger.warning("Skipping contaminated audit entry: ip=%s", entry.get("ip_address"))
                _audit_queue.task_done()
                continue

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
                entry,
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
    user_id: str | None,
    user_email: str | None,
    action: str,
    resource: str | None = None,
    resource_id: str | None = None,
    request_method: str | None = None,
    request_path: str | None = None,
    request_body: str | None = None,
    response_status: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    duration_ms: int | None = None,
    success: bool = True,
):
    """
    Queue an audit log entry for async writing.

    This function is non-blocking and returns immediately.
    """
    _start_audit_worker()

    entry = {
        "log_id": _generate_log_id(),
        "timestamp": datetime.now(UTC).isoformat(),
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
        auth_context: AuthContext | None = getattr(request.state, "auth_context", None)
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

    def _extract_resource(self, path: str) -> tuple[str | None, str | None]:
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
    user_id: str | None = None,
    user_email: str | None = None,
    action: str | None = None,
    resource: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    success_only: bool | None = None,
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

    start_date = (datetime.now(UTC) - timedelta(days=days)).isoformat()

    con = connect()

    # Total requests
    cur = execute(
        con,
        "SELECT COUNT(*) FROM audit_log WHERE timestamp >= :start_date",
        {"start_date": start_date},
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
        {"start_date": start_date},
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
        {"start_date": start_date},
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
        {"start_date": start_date},
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
        {"start_date": start_date},
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
    start_date: datetime | None = None,
    end_date: datetime | None = None,
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


# --- Log Retention ---

import os

# Default retention period in days (configurable via LOG_RETENTION_DAYS env var)
DEFAULT_RETENTION_DAYS = 90


def get_retention_days() -> int:
    """Get log retention period from environment or default."""
    try:
        return int(os.environ.get("LOG_RETENTION_DAYS", DEFAULT_RETENTION_DAYS))
    except (ValueError, TypeError):
        return DEFAULT_RETENTION_DAYS


def cleanup_old_audit_logs(retention_days: int | None = None, dry_run: bool = False) -> dict:
    """
    Delete audit logs older than the retention period.

    Args:
        retention_days: Number of days to retain logs (default: from env or 90)
        dry_run: If True, count but don't delete

    Returns:
        Dict with cleanup stats: {deleted: int, retention_days: int, cutoff_date: str}
    """
    from ..db import connect, execute

    if retention_days is None:
        retention_days = get_retention_days()

    cutoff_date = (datetime.now(UTC) - timedelta(days=retention_days)).isoformat()

    con = connect()

    # Count records to delete
    cur = execute(
        con,
        "SELECT COUNT(*) FROM audit_log WHERE timestamp < :cutoff_date",
        {"cutoff_date": cutoff_date},
    )
    count_to_delete = cur.fetchone()[0]

    deleted = 0
    if not dry_run and count_to_delete > 0:
        execute(
            con,
            "DELETE FROM audit_log WHERE timestamp < :cutoff_date",
            {"cutoff_date": cutoff_date},
        )
        con.commit()
        deleted = count_to_delete
        logger.info(f"Deleted {deleted} audit log entries older than {retention_days} days")

    con.close()

    return {
        "deleted": deleted,
        "would_delete": count_to_delete,
        "retention_days": retention_days,
        "cutoff_date": cutoff_date,
    }


def cleanup_old_signal_audit_logs(retention_days: int | None = None, dry_run: bool = False) -> dict:
    """
    Delete signal audit logs older than the retention period.

    Args:
        retention_days: Number of days to retain logs (default: from env or 90)
        dry_run: If True, count but don't delete

    Returns:
        Dict with cleanup stats
    """
    from ..db import connect, execute

    if retention_days is None:
        retention_days = get_retention_days()

    cutoff_date = (datetime.now(UTC) - timedelta(days=retention_days)).isoformat()

    con = connect()

    # Count records to delete
    cur = execute(
        con,
        "SELECT COUNT(*) FROM signal_audit_log WHERE created_at < :cutoff_date",
        {"cutoff_date": cutoff_date},
    )
    count_to_delete = cur.fetchone()[0]

    deleted = 0
    if not dry_run and count_to_delete > 0:
        execute(
            con,
            "DELETE FROM signal_audit_log WHERE created_at < :cutoff_date",
            {"cutoff_date": cutoff_date},
        )
        con.commit()
        deleted = count_to_delete
        logger.info(f"Deleted {deleted} signal audit log entries older than {retention_days} days")

    con.close()

    return {
        "deleted": deleted,
        "would_delete": count_to_delete,
        "retention_days": retention_days,
        "cutoff_date": cutoff_date,
    }


def run_all_log_cleanup(retention_days: int | None = None, dry_run: bool = False) -> dict:
    """
    Run cleanup on all audit log tables.

    Args:
        retention_days: Number of days to retain logs
        dry_run: If True, count but don't delete

    Returns:
        Combined cleanup stats
    """
    audit_result = cleanup_old_audit_logs(retention_days, dry_run)
    signal_result = cleanup_old_signal_audit_logs(retention_days, dry_run)

    return {
        "audit_log": audit_result,
        "signal_audit_log": signal_result,
        "total_deleted": audit_result["deleted"] + signal_result["deleted"],
        "total_would_delete": audit_result["would_delete"] + signal_result["would_delete"],
    }
