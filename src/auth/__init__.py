"""
Authentication Module for VA Signals Command Dashboard

Provides:
- Firebase Authentication (email/password, Google OAuth)
- IAP fallback authentication
- Role-based access control (RBAC)
- Session management
- Audit logging
"""

from .firebase_config import init_firebase, verify_firebase_token
from .middleware import AuthMiddleware, get_current_user, require_auth, require_role
from .models import User, UserRole, AuthContext
from .api import router as auth_router
from .rbac import (
    Permission,
    has_permission,
    get_permissions_for_role,
    require_permission,
    require_minimum_role,
    ResourceAccess,
    get_resource_access,
)
from .audit import (
    AuditMiddleware,
    log_audit,
    get_audit_logs,
    get_audit_stats,
    export_audit_logs_csv,
)

__all__ = [
    # Firebase
    "init_firebase",
    "verify_firebase_token",
    # Middleware
    "AuthMiddleware",
    "get_current_user",
    "require_auth",
    "require_role",
    # Models
    "User",
    "UserRole",
    "AuthContext",
    # RBAC
    "Permission",
    "has_permission",
    "get_permissions_for_role",
    "require_permission",
    "require_minimum_role",
    "ResourceAccess",
    "get_resource_access",
    # Audit
    "AuditMiddleware",
    "log_audit",
    "get_audit_logs",
    "get_audit_stats",
    "export_audit_logs_csv",
    # Router
    "auth_router",
]
