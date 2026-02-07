"""
Authentication Data Models

Pydantic models for users, sessions, and audit records.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class UserRole(str, Enum):
    """User role hierarchy for RBAC."""

    COMMANDER = "commander"  # Full access, user management
    LEADERSHIP = "leadership"  # Read all, write posture/tasks
    ANALYST = "analyst"  # Read all, generate reports
    VIEWER = "viewer"  # Read dashboards only


class User(BaseModel):
    """User account model."""

    user_id: str
    email: str
    display_name: str | None = None
    role: UserRole = UserRole.VIEWER
    created_at: datetime | None = None
    last_login: datetime | None = None
    is_active: bool = True


class AuthContext(BaseModel):
    """Authentication context passed through middleware."""

    user_id: str
    email: str
    display_name: str | None = None
    role: UserRole
    auth_method: str  # "firebase", "iap", "session"
    token_issued_at: datetime | None = None
    token_expires_at: datetime | None = None


class Session(BaseModel):
    """User session for cookie-based auth."""

    session_id: str
    user_id: str
    created_at: datetime
    expires_at: datetime
    ip_address: str | None = None
    user_agent: str | None = None
    is_valid: bool = True


class AuditLog(BaseModel):
    """Audit log entry for request tracking."""

    log_id: str
    timestamp: datetime
    user_id: str | None = None
    user_email: str | None = None
    action: str
    resource: str | None = None
    resource_id: str | None = None
    request_method: str
    request_path: str
    request_body: str | None = None
    response_status: int
    ip_address: str | None = None
    user_agent: str | None = None
    duration_ms: int
    success: bool


# --- API Request/Response Models ---


class LoginRequest(BaseModel):
    """Email/password login request."""

    email: str
    password: str


class LoginResponse(BaseModel):
    """Login response with token."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: User


class TokenVerifyRequest(BaseModel):
    """Token verification request."""

    token: str


class TokenVerifyResponse(BaseModel):
    """Token verification response."""

    valid: bool
    user_id: str | None = None
    email: str | None = None
    role: str | None = None
    expires_at: str | None = None


class UserCreateRequest(BaseModel):
    """Request to create/invite a new user."""

    email: str
    display_name: str | None = None
    role: UserRole = UserRole.VIEWER


class UserUpdateRequest(BaseModel):
    """Request to update user role or status."""

    role: UserRole | None = None
    is_active: bool | None = None
    display_name: str | None = None


class CurrentUserResponse(BaseModel):
    """Response for /auth/me endpoint."""

    user_id: str
    email: str
    display_name: str | None = None
    role: str
    permissions: list[str]


class SessionCreateRequest(BaseModel):
    """Request to create session from Firebase ID token."""

    idToken: str
    provider: str = "google"  # "google" or "email"
    rememberMe: bool = False


class FirebaseConfigResponse(BaseModel):
    """Firebase client configuration for frontend."""

    apiKey: str
    authDomain: str
    projectId: str
    storageBucket: str | None = None
    messagingSenderId: str | None = None
    appId: str | None = None
