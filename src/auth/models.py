"""
Authentication Data Models

Pydantic models for users, sessions, and audit records.
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, EmailStr


class UserRole(str, Enum):
    """User role hierarchy for RBAC."""
    COMMANDER = "commander"      # Full access, user management
    LEADERSHIP = "leadership"    # Read all, write posture/tasks
    ANALYST = "analyst"          # Read all, generate reports
    VIEWER = "viewer"            # Read dashboards only


class User(BaseModel):
    """User account model."""
    user_id: str
    email: str
    display_name: Optional[str] = None
    role: UserRole = UserRole.VIEWER
    created_at: Optional[datetime] = None
    last_login: Optional[datetime] = None
    is_active: bool = True


class AuthContext(BaseModel):
    """Authentication context passed through middleware."""
    user_id: str
    email: str
    display_name: Optional[str] = None
    role: UserRole
    auth_method: str  # "firebase", "iap", "session"
    token_issued_at: Optional[datetime] = None
    token_expires_at: Optional[datetime] = None


class Session(BaseModel):
    """User session for cookie-based auth."""
    session_id: str
    user_id: str
    created_at: datetime
    expires_at: datetime
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    is_valid: bool = True


class AuditLog(BaseModel):
    """Audit log entry for request tracking."""
    log_id: str
    timestamp: datetime
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    action: str
    resource: Optional[str] = None
    resource_id: Optional[str] = None
    request_method: str
    request_path: str
    request_body: Optional[str] = None
    response_status: int
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
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
    user_id: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    expires_at: Optional[str] = None


class UserCreateRequest(BaseModel):
    """Request to create/invite a new user."""
    email: str
    display_name: Optional[str] = None
    role: UserRole = UserRole.VIEWER


class UserUpdateRequest(BaseModel):
    """Request to update user role or status."""
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    display_name: Optional[str] = None


class CurrentUserResponse(BaseModel):
    """Response for /auth/me endpoint."""
    user_id: str
    email: str
    display_name: Optional[str] = None
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
    storageBucket: Optional[str] = None
    messagingSenderId: Optional[str] = None
    appId: Optional[str] = None
