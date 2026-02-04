"""
Authentication Middleware

Provides:
- Dual-auth support (Firebase + IAP)
- Session cookie validation
- CSRF protection
- Request context injection
"""

import os
import secrets
import logging
from typing import Optional, Callable
from functools import wraps

from fastapi import Request, Response, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware

from .firebase_config import (
    verify_firebase_token,
    verify_iap_token,
    verify_session_token,
    init_firebase,
)
from .models import AuthContext, UserRole

logger = logging.getLogger(__name__)

# Security scheme for OpenAPI docs
bearer_scheme = HTTPBearer(auto_error=False)

# Paths that don't require authentication
PUBLIC_PATHS = {
    "/",
    "/health",
    "/api/auth/login",
    "/api/auth/verify",
    "/docs",
    "/openapi.json",
    "/redoc",
}

# Paths that should skip auth (static files, etc.)
SKIP_AUTH_PREFIXES = [
    "/static",
    "/_next",
    "/favicon",
]

# Session cookie name
SESSION_COOKIE_NAME = "va_signals_session"

# CSRF token header name
CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_COOKIE_NAME = "csrf_token"


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Authentication middleware supporting multiple auth methods.

    Priority order:
    1. Firebase token (Authorization: Bearer <token>)
    2. IAP JWT (X-Goog-IAP-JWT-Assertion header)
    3. Session cookie (va_signals_session)

    Sets request.state.auth_context on successful auth.
    """

    def __init__(self, app, require_auth: bool = True):
        super().__init__(app)
        self.require_auth = require_auth
        # Initialize Firebase on startup
        init_firebase()

    async def dispatch(self, request: Request, call_next):
        # Check if path should skip auth
        path = request.url.path

        if self._should_skip_auth(path):
            return await call_next(request)

        # Try authentication methods in order
        auth_context = await self._authenticate(request)

        if auth_context:
            request.state.auth_context = auth_context
            request.state.user = auth_context.email  # For logging compatibility
        elif self.require_auth and path not in PUBLIC_PATHS:
            return Response(
                status_code=401,
                content="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        else:
            request.state.auth_context = None

        # CSRF check for state-changing methods
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            if not self._verify_csrf(request):
                # For API calls, we can be lenient if they have Bearer auth
                if not auth_context or auth_context.auth_method == "session":
                    return Response(
                        status_code=403,
                        content="CSRF token missing or invalid",
                    )

        response = await call_next(request)
        return response

    def _should_skip_auth(self, path: str) -> bool:
        """Check if path should skip authentication."""
        if path in PUBLIC_PATHS:
            return True
        for prefix in SKIP_AUTH_PREFIXES:
            if path.startswith(prefix):
                return True
        return False

    async def _authenticate(self, request: Request) -> Optional[AuthContext]:
        """Try all authentication methods."""

        # Method 1: Firebase Bearer token
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
            claims = verify_firebase_token(token)
            if claims:
                return await self._build_auth_context(claims, "firebase")

        # Method 2: IAP JWT
        iap_jwt = request.headers.get("X-Goog-IAP-JWT-Assertion")
        if iap_jwt:
            claims = verify_iap_token(iap_jwt)
            if claims:
                return await self._build_auth_context(claims, "iap")

        # Method 3: Session cookie
        session_token = request.cookies.get(SESSION_COOKIE_NAME)
        if session_token:
            claims = verify_session_token(session_token)
            if claims:
                return await self._build_auth_context(claims, "session")

        return None

    async def _build_auth_context(self, claims: dict, auth_method: str) -> AuthContext:
        """Build AuthContext from token claims."""
        from datetime import datetime, timezone

        # Look up user role from database
        role = await self._get_user_role(claims.get("user_id"), claims.get("email"))

        return AuthContext(
            user_id=claims.get("user_id", ""),
            email=claims.get("email", ""),
            display_name=claims.get("display_name"),
            role=role,
            auth_method=auth_method,
            token_issued_at=datetime.fromtimestamp(claims["iat"], tz=timezone.utc) if claims.get("iat") else None,
            token_expires_at=datetime.fromtimestamp(claims["exp"], tz=timezone.utc) if claims.get("exp") else None,
        )

    async def _get_user_role(self, user_id: Optional[str], email: Optional[str]) -> UserRole:
        """Look up user role from database."""
        if not user_id and not email:
            return UserRole.VIEWER

        try:
            from ..db import connect, execute

            con = connect()
            cur = execute(
                con,
                """SELECT role FROM users
                   WHERE user_id = :user_id OR email = :email
                   LIMIT 1""",
                {"user_id": user_id, "email": email}
            )
            row = cur.fetchone()
            con.close()

            if row:
                return UserRole(row[0])

        except Exception as e:
            logger.debug(f"Could not look up user role: {e}")

        # Default to viewer if not found
        return UserRole.VIEWER

    def _verify_csrf(self, request: Request) -> bool:
        """Verify CSRF token matches cookie."""
        csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)
        csrf_header = request.headers.get(CSRF_HEADER_NAME)

        if not csrf_cookie or not csrf_header:
            return False

        return secrets.compare_digest(csrf_cookie, csrf_header)


def get_current_user(request: Request) -> Optional[AuthContext]:
    """
    Dependency to get current authenticated user.

    Usage:
        @app.get("/api/me")
        async def me(user: AuthContext = Depends(get_current_user)):
            return {"email": user.email}
    """
    return getattr(request.state, "auth_context", None)


def require_auth(request: Request) -> AuthContext:
    """
    Dependency that requires authentication.

    Raises HTTPException 401 if not authenticated.

    Usage:
        @app.get("/api/protected")
        async def protected(user: AuthContext = Depends(require_auth)):
            return {"email": user.email}
    """
    auth_context = getattr(request.state, "auth_context", None)
    if not auth_context:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return auth_context


def require_role(*roles: UserRole):
    """
    Dependency factory that requires specific roles.

    Usage:
        @app.get("/api/admin")
        async def admin(user: AuthContext = Depends(require_role(UserRole.COMMANDER))):
            return {"admin": True}
    """
    def dependency(request: Request) -> AuthContext:
        auth_context = require_auth(request)
        if auth_context.role not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"Requires one of roles: {[r.value for r in roles]}",
            )
        return auth_context
    return dependency


def require_commander(request: Request) -> AuthContext:
    """Shortcut for require_role(UserRole.COMMANDER)."""
    return require_role(UserRole.COMMANDER)(request)


def require_leadership_or_above(request: Request) -> AuthContext:
    """Require leadership or commander role."""
    return require_role(UserRole.COMMANDER, UserRole.LEADERSHIP)(request)


def generate_csrf_token() -> str:
    """Generate a new CSRF token."""
    return secrets.token_urlsafe(32)


def set_auth_cookies(response: Response, session_token: str, csrf_token: str):
    """Set authentication cookies on response."""
    # Session cookie - httpOnly for security
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        secure=os.environ.get("ENV", "development") == "production",
        samesite="lax",
        max_age=86400,  # 24 hours
    )

    # CSRF cookie - NOT httpOnly so JS can read it
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,
        secure=os.environ.get("ENV", "development") == "production",
        samesite="strict",
        max_age=86400,
    )


def clear_auth_cookies(response: Response):
    """Clear authentication cookies (logout)."""
    response.delete_cookie(SESSION_COOKIE_NAME)
    response.delete_cookie(CSRF_COOKIE_NAME)
