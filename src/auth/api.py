"""
Authentication API Endpoints

Provides:
- Login (email/password via Firebase)
- Token verification
- Session management
- User management (commander only)
- Current user info
"""

import os
import time
import uuid
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response, Depends, Query

from .models import (
    User,
    UserRole,
    AuthContext,
    LoginRequest,
    LoginResponse,
    TokenVerifyRequest,
    TokenVerifyResponse,
    UserCreateRequest,
    UserUpdateRequest,
    CurrentUserResponse,
    SessionCreateRequest,
    FirebaseConfigResponse,
)
from .middleware import (
    get_current_user,
    require_auth,
    require_role,
    generate_csrf_token,
    set_auth_cookies,
    clear_auth_cookies,
)
from .firebase_config import (
    verify_firebase_token,
    create_session_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["authentication"])


# =============================================================================
# PER-IP RATE LIMITER FOR AUTH ENDPOINTS
# =============================================================================

class _AuthRateLimiter:
    """
    Per-IP token bucket rate limiter for authentication endpoints.

    Prevents brute-force attacks by limiting login attempts per IP.
    Defaults: 5 attempts burst, refill 1 token per 5 seconds (12/min sustained).
    Stale entries are cleaned up every 1000 requests to prevent memory leaks.
    """

    def __init__(self, burst: int = 5, refill_rate: float = 0.2):
        self._buckets: dict[str, list] = {}  # ip -> [tokens, last_update]
        self._burst = burst
        self._refill_rate = refill_rate  # tokens per second
        self._request_count = 0

    def reset(self) -> None:
        """Clear all rate limit state (for testing)."""
        self._buckets.clear()
        self._request_count = 0

    def check(self, ip: str) -> tuple[bool, float]:
        """
        Check if request from IP is allowed.

        Returns:
            (allowed, retry_after_seconds)
        """
        now = time.time()
        self._request_count += 1

        # Periodic cleanup of stale entries (>10 min idle)
        if self._request_count % 1000 == 0:
            cutoff = now - 600
            self._buckets = {
                k: v for k, v in self._buckets.items() if v[1] > cutoff
            }

        if ip not in self._buckets:
            self._buckets[ip] = [float(self._burst), now]

        bucket = self._buckets[ip]
        elapsed = now - bucket[1]
        bucket[0] = min(self._burst, bucket[0] + elapsed * self._refill_rate)
        bucket[1] = now

        if bucket[0] >= 1.0:
            bucket[0] -= 1.0
            return True, 0.0
        else:
            retry_after = (1.0 - bucket[0]) / self._refill_rate
            return False, retry_after


# Singleton — shared across all auth endpoints
_auth_limiter = _AuthRateLimiter(
    burst=int(os.environ.get("AUTH_RATE_LIMIT_BURST", "5")),
    refill_rate=float(os.environ.get("AUTH_RATE_LIMIT_RATE", "0.2")),
)


def _get_client_ip(request: Request) -> str:
    """Extract client IP, respecting X-Forwarded-For behind Cloud Run proxy."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_auth_rate_limit(request: Request) -> None:
    """FastAPI dependency that enforces auth rate limiting."""
    ip = _get_client_ip(request)
    allowed, retry_after = _auth_limiter.check(ip)
    if not allowed:
        logger.warning(f"Auth rate limit exceeded for IP {ip}")
        raise HTTPException(
            status_code=429,
            detail="Too many authentication attempts. Please try again later.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )


# --- Firebase Config Endpoint ---

@router.get("/config", response_model=FirebaseConfigResponse)
async def get_firebase_config():
    """
    Get Firebase client configuration for frontend authentication.

    This returns the PUBLIC Firebase config needed by the frontend JS SDK.
    These are NOT secrets - they're meant to be public.
    """
    import os

    api_key = os.environ.get("FIREBASE_API_KEY")
    project_id = os.environ.get("FIREBASE_PROJECT_ID", "vetclaims-ai")

    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Firebase not configured. Set FIREBASE_API_KEY environment variable."
        )

    return FirebaseConfigResponse(
        apiKey=api_key,
        authDomain=f"{project_id}.firebaseapp.com",
        projectId=project_id,
        storageBucket=os.environ.get("FIREBASE_STORAGE_BUCKET", f"{project_id}.appspot.com"),
        messagingSenderId=os.environ.get("FIREBASE_MESSAGING_SENDER_ID"),
        appId=os.environ.get("FIREBASE_APP_ID"),
    )


# --- Database Helpers ---

def _get_db():
    """Get database connection."""
    from ..db import connect
    return connect()


def _execute(sql: str, params: dict = None):
    """Execute a query and return results as list of dicts."""
    from ..db import connect, execute, get_db_backend
    con = connect()
    if get_db_backend() == "postgres":
        # psycopg uses cursor-level row_factory via dict_row
        from psycopg.rows import dict_row
        cur = con.cursor(row_factory=dict_row)
        from ..db import _prepare_query
        sql, params = _prepare_query(sql, params)
        if params is None:
            cur.execute(sql)
        else:
            cur.execute(sql, params)
    else:
        # sqlite3 uses connection-level row_factory
        con.row_factory = lambda cursor, row: dict(
            zip([col[0] for col in cursor.description], row)
        )
        cur = execute(con, sql, params)
    results = cur.fetchall()
    con.close()
    return results


def _execute_write(sql: str, params: dict = None):
    """Execute a write query."""
    from ..db import connect, execute
    con = connect()
    execute(con, sql, params)
    con.commit()
    con.close()


def _get_user_by_email(email: str) -> Optional[dict]:
    """Get user by email."""
    results = _execute(
        "SELECT * FROM users WHERE email = :email AND is_active = TRUE",
        {"email": email}
    )
    return results[0] if results else None


def _get_user_by_id(user_id: str) -> Optional[dict]:
    """Get user by ID."""
    results = _execute(
        "SELECT * FROM users WHERE user_id = :user_id",
        {"user_id": user_id}
    )
    return results[0] if results else None


def _create_or_update_user(user_id: str, email: str, display_name: str = None) -> dict:
    """Create user if not exists, or update existing user's login time."""
    existing = _get_user_by_email(email)

    if existing:
        # Update last login and possibly link user_id
        _execute_write(
            """UPDATE users
               SET last_login = :now, user_id = :user_id,
                   display_name = COALESCE(:display_name, display_name)
               WHERE email = :email""",
            {
                "now": datetime.now(timezone.utc).isoformat(),
                "user_id": user_id,
                "email": email,
                "display_name": display_name,
            }
        )
        return _get_user_by_email(email)
    else:
        # Create new user with viewer role
        _execute_write(
            """INSERT INTO users (user_id, email, display_name, role, created_at, last_login)
               VALUES (:user_id, :email, :display_name, 'viewer', :now, :now)""",
            {
                "user_id": user_id,
                "email": email,
                "display_name": display_name or email.split("@")[0],
                "now": datetime.now(timezone.utc).isoformat(),
            }
        )
        return _get_user_by_email(email)


def _init_auth_tables():
    """Initialize auth database tables."""
    from ..db import init_db
    init_db()
    logger.info("Auth tables initialized")


# --- Permission Helpers ---

ROLE_PERMISSIONS = {
    UserRole.COMMANDER: [
        "read:all",
        "write:all",
        "manage:users",
        "export:all",
        "audit:view",
    ],
    UserRole.LEADERSHIP: [
        "read:all",
        "write:posture",
        "write:tasks",
        "export:reports",
    ],
    UserRole.ANALYST: [
        "read:all",
        "export:reports",
    ],
    UserRole.VIEWER: [
        "read:dashboard",
    ],
}


def get_permissions(role: UserRole) -> list[str]:
    """Get permissions for a role."""
    return ROLE_PERMISSIONS.get(role, [])


# --- Endpoints ---

@router.post("/login", dependencies=[Depends(_check_auth_rate_limit)])
async def login(request: Request, response: Response, body: LoginRequest):
    """
    Login with email/password via Firebase.

    Returns session token and sets cookies.

    Note: This endpoint expects the client to have already authenticated
    with Firebase on the frontend and obtained an ID token.
    The 'password' field is actually the Firebase ID token.
    """
    # In a real implementation, the password would be the Firebase ID token
    # obtained by the client after Firebase email/password auth
    firebase_token = body.password  # This is actually the Firebase ID token

    # Verify the token
    claims = verify_firebase_token(firebase_token)
    if not claims:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Check email matches
    if claims.get("email") != body.email:
        raise HTTPException(status_code=401, detail="Email mismatch")

    # Create or update user in database
    user_data = _create_or_update_user(
        user_id=claims["user_id"],
        email=claims["email"],
        display_name=claims.get("display_name"),
    )

    # Create session token
    session_token = create_session_token(
        user_id=user_data["user_id"],
        email=user_data["email"],
    )

    # Generate CSRF token
    csrf_token = generate_csrf_token()

    # Set cookies
    set_auth_cookies(response, session_token, csrf_token)

    return {
        "status": "success",
        "user": {
            "user_id": user_data["user_id"],
            "email": user_data["email"],
            "display_name": user_data.get("display_name"),
            "role": user_data["role"],
        },
        "csrf_token": csrf_token,
    }


@router.post("/session", dependencies=[Depends(_check_auth_rate_limit)])
async def create_session(request: Request, response: Response, body: SessionCreateRequest):
    """
    Create a backend session from a Firebase ID token.

    This is called by the frontend after Firebase authentication.
    The frontend sends the Firebase ID token, and we verify it
    and create a server-side session.
    """
    # Verify the Firebase ID token
    claims = verify_firebase_token(body.idToken)
    if not claims:
        raise HTTPException(status_code=401, detail="Invalid Firebase token")

    # Create or update user in database
    user_data = _create_or_update_user(
        user_id=claims["user_id"],
        email=claims["email"],
        display_name=claims.get("display_name"),
    )

    # Create session token with appropriate expiration
    expires_hours = 24 * 30 if body.rememberMe else 24  # 30 days vs 1 day
    session_token = create_session_token(
        user_id=user_data["user_id"],
        email=user_data["email"],
        expires_in_hours=expires_hours,
    )

    # Generate CSRF token
    csrf_token = generate_csrf_token()

    # Set cookies
    set_auth_cookies(response, session_token, csrf_token)

    logger.info(f"Session created for user {user_data['email']} via {body.provider}")

    return {
        "status": "success",
        "user": {
            "user_id": user_data["user_id"],
            "email": user_data["email"],
            "display_name": user_data.get("display_name"),
            "role": user_data["role"],
        },
        "csrf_token": csrf_token,
    }


@router.get("/google")
async def google_oauth_redirect(request: Request):
    """
    Fallback Google OAuth redirect.

    This endpoint is only used when Firebase SDK fails to load on the frontend.
    It redirects to Google's OAuth consent screen.

    Note: For this to work, you need to configure OAuth credentials in
    Google Cloud Console and set GOOGLE_CLIENT_ID environment variable.
    """
    import os
    from urllib.parse import urlencode

    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    if not client_id:
        raise HTTPException(
            status_code=503,
            detail="Google OAuth not configured. Please use Firebase Sign-In instead, or configure GOOGLE_CLIENT_ID."
        )

    # Build the OAuth URL
    redirect_uri = str(request.url_for("google_oauth_callback"))

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account",
    }

    oauth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=oauth_url)


@router.get("/google/callback")
async def google_oauth_callback(
    request: Request,
    response: Response,
    code: str = Query(None),
    error: str = Query(None),
):
    """
    Handle OAuth callback from Google.

    Exchanges the authorization code for tokens and creates a session.
    """
    import os
    import httpx

    if error:
        # Redirect to login with error
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=f"/login.html?error={error}")

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise HTTPException(status_code=503, detail="OAuth not configured")

    # Exchange code for tokens
    redirect_uri = str(request.url_for("google_oauth_callback"))

    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
        )

        if token_response.status_code != 200:
            logger.error(f"Token exchange failed: {token_response.text}")
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url="/login.html?error=token_exchange_failed")

        tokens = token_response.json()

        # Get user info
        userinfo_response = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )

        if userinfo_response.status_code != 200:
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url="/login.html?error=userinfo_failed")

        userinfo = userinfo_response.json()

    # Create or update user
    user_data = _create_or_update_user(
        user_id=userinfo.get("id", userinfo.get("email")),
        email=userinfo["email"],
        display_name=userinfo.get("name"),
    )

    # Create session
    session_token = create_session_token(
        user_id=user_data["user_id"],
        email=user_data["email"],
    )

    csrf_token = generate_csrf_token()
    set_auth_cookies(response, session_token, csrf_token)

    logger.info(f"OAuth login successful for {user_data['email']}")

    # Redirect to dashboard
    from fastapi.responses import RedirectResponse
    redirect_response = RedirectResponse(url="/", status_code=302)
    set_auth_cookies(redirect_response, session_token, csrf_token)
    return redirect_response


@router.post("/verify", dependencies=[Depends(_check_auth_rate_limit)])
async def verify_token(request: Request, body: TokenVerifyRequest):
    """
    Verify a Firebase ID token.

    Returns token validity and user info if valid.
    """
    claims = verify_firebase_token(body.token)

    if not claims:
        return TokenVerifyResponse(valid=False)

    # Look up user role
    user = _get_user_by_email(claims.get("email", ""))
    role = user["role"] if user else "viewer"

    return TokenVerifyResponse(
        valid=True,
        user_id=claims.get("user_id"),
        email=claims.get("email"),
        role=role,
        expires_at=datetime.fromtimestamp(claims["exp"], tz=timezone.utc).isoformat() if claims.get("exp") else None,
    )


@router.post("/logout")
async def logout(response: Response, user: AuthContext = Depends(get_current_user)):
    """
    Logout - clears session cookies.
    """
    clear_auth_cookies(response)
    return {"status": "logged_out"}


@router.get("/me", response_model=CurrentUserResponse)
async def get_me(user: AuthContext = Depends(require_auth)):
    """
    Get current user info and permissions.
    """
    return CurrentUserResponse(
        user_id=user.user_id,
        email=user.email,
        display_name=user.display_name,
        role=user.role.value,
        permissions=get_permissions(user.role),
    )


@router.get("/csrf")
async def get_csrf_token(response: Response):
    """
    Get a CSRF token for form submissions.

    Sets the CSRF cookie and returns the token.
    """
    csrf_token = generate_csrf_token()
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,
        samesite="strict",
        max_age=86400,
    )
    return {"csrf_token": csrf_token}


# --- User Management (Commander Only) ---

@router.get("/users")
async def list_users(
    role: Optional[str] = Query(None, description="Filter by role"),
    user: AuthContext = Depends(require_role(UserRole.COMMANDER)),
):
    """
    List all users (commander only).
    """
    if role:
        users = _execute(
            "SELECT user_id, email, display_name, role, created_at, last_login, is_active FROM users WHERE role = :role ORDER BY created_at DESC",
            {"role": role}
        )
    else:
        users = _execute(
            "SELECT user_id, email, display_name, role, created_at, last_login, is_active FROM users ORDER BY created_at DESC"
        )

    return {"users": users, "count": len(users)}


@router.post("/users")
async def create_user(
    body: UserCreateRequest,
    user: AuthContext = Depends(require_role(UserRole.COMMANDER)),
):
    """
    Create/invite a new user (commander only).

    Creates a user record. The user will be linked to their
    Firebase account on first login.
    """
    # Check if user already exists
    existing = _get_user_by_email(body.email)
    if existing:
        raise HTTPException(status_code=400, detail="User with this email already exists")

    # Create pending user
    user_id = f"pending-{uuid.uuid4().hex[:8]}"

    _execute_write(
        """INSERT INTO users (user_id, email, display_name, role, created_at, created_by)
           VALUES (:user_id, :email, :display_name, :role, :now, :created_by)""",
        {
            "user_id": user_id,
            "email": body.email,
            "display_name": body.display_name or body.email.split("@")[0],
            "role": body.role.value,
            "now": datetime.now(timezone.utc).isoformat(),
            "created_by": user.user_id,
        }
    )

    new_user = _get_user_by_email(body.email)

    return {"status": "created", "user": new_user}


@router.patch("/users/{target_user_id}")
async def update_user(
    target_user_id: str,
    body: UserUpdateRequest,
    user: AuthContext = Depends(require_role(UserRole.COMMANDER)),
):
    """
    Update a user's role or status (commander only).
    """
    target = _get_user_by_id(target_user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    # Build update
    updates = []
    params = {"user_id": target_user_id}

    if body.role is not None:
        updates.append("role = :role")
        params["role"] = body.role.value

    if body.is_active is not None:
        updates.append("is_active = :is_active")
        params["is_active"] = body.is_active

    if body.display_name is not None:
        updates.append("display_name = :display_name")
        params["display_name"] = body.display_name

    if updates:
        _execute_write(
            f"UPDATE users SET {', '.join(updates)} WHERE user_id = :user_id",
            params
        )

    updated_user = _get_user_by_id(target_user_id)
    return {"status": "updated", "user": updated_user}


@router.delete("/users/{target_user_id}")
async def deactivate_user(
    target_user_id: str,
    user: AuthContext = Depends(require_role(UserRole.COMMANDER)),
):
    """
    Deactivate a user (commander only).

    Does not delete - just sets is_active to FALSE.
    """
    target = _get_user_by_id(target_user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent self-deactivation
    if target_user_id == user.user_id:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")

    _execute_write(
        "UPDATE users SET is_active = FALSE WHERE user_id = :user_id",
        {"user_id": target_user_id}
    )

    return {"status": "deactivated", "user_id": target_user_id}


@router.post("/init")
async def init_tables(user: AuthContext = Depends(require_auth)):
    """
    Initialize authentication database tables.

    Requires authentication (Commander role recommended for production use).
    """
    try:
        _init_auth_tables()
        return {"status": "initialized"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Audit Endpoints (Commander Only) ---

@router.get("/audit/logs")
async def get_audit_log_entries(
    user_email: Optional[str] = Query(None, description="Filter by user email"),
    action: Optional[str] = Query(None, description="Filter by action (partial match)"),
    resource: Optional[str] = Query(None, description="Filter by resource type"),
    days: int = Query(7, ge=1, le=90, description="Number of days to look back"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    user: AuthContext = Depends(require_role(UserRole.COMMANDER)),
):
    """
    Query audit logs (commander only).

    Returns paginated audit log entries with filtering options.
    """
    from .audit import get_audit_logs
    from datetime import timedelta

    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    logs = get_audit_logs(
        user_email=user_email,
        action=action,
        resource=resource,
        start_date=start_date,
        limit=limit,
        offset=offset,
    )

    return {
        "logs": logs,
        "count": len(logs),
        "limit": limit,
        "offset": offset,
    }


@router.get("/audit/stats")
async def get_audit_statistics(
    days: int = Query(7, ge=1, le=90, description="Number of days for statistics"),
    user: AuthContext = Depends(require_role(UserRole.COMMANDER)),
):
    """
    Get audit statistics (commander only).

    Returns summary stats for the specified period.
    """
    from .audit import get_audit_stats

    stats = get_audit_stats(days=days)
    return stats


@router.get("/audit/export")
async def export_audit_logs(
    days: int = Query(30, ge=1, le=365, description="Number of days to export"),
    user: AuthContext = Depends(require_role(UserRole.COMMANDER)),
):
    """
    Export audit logs to CSV (commander only).

    Returns CSV file for download.
    """
    from fastapi.responses import StreamingResponse
    from .audit import export_audit_logs_csv
    from datetime import timedelta
    import io

    start_date = datetime.now(timezone.utc) - timedelta(days=days)
    csv_content = export_audit_logs_csv(start_date=start_date)

    # Create streaming response
    output = io.BytesIO(csv_content.encode("utf-8"))
    output.seek(0)

    filename = f"audit_log_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"

    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
