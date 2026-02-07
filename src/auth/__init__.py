"""
Authentication Module for VA Signals Command Dashboard

Provides:
- Firebase Authentication (email/password, Google OAuth)
- IAP fallback authentication
- Role-based access control (RBAC)
- Session management
- Audit logging
"""

from .api import router as auth_router
from .audit import (
    AuditMiddleware,
    export_audit_logs_csv,
    get_audit_logs,
    get_audit_stats,
    log_audit,
)
from .firebase_config import init_firebase, verify_firebase_token
from .middleware import AuthMiddleware, get_current_user, require_auth, require_role
from .models import AuthContext, User, UserRole
from .rbac import (
    Permission,
    ResourceAccess,
    get_permissions_for_role,
    get_resource_access,
    has_permission,
    require_minimum_role,
    require_permission,
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
