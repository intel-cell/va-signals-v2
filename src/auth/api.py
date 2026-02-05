"""
Authentication API Endpoints

Provides:
- Login (email/password via Firebase)
- Token verification
- Session management
- User management (commander only)
- Current user info
"""

import uuid
import logging
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


# --- Database Helpers ---

def _get_db():
    """Get database connection."""
    from ..db import connect
    return connect()


def _execute(sql: str, params: dict = None):
    """Execute a query and return results."""
    from ..db import connect, execute
    con = connect()
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

@router.post("/login")
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


@router.post("/verify")
async def verify_token(body: TokenVerifyRequest):
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
async def init_tables():
    """
    Initialize authentication database tables.

    This is an admin endpoint for setup.
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
