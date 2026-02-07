"""
Role-Based Access Control (RBAC) Module

Provides:
- Role hierarchy definition
- Permission checking functions
- Decorators for endpoint protection
- Resource-level access control
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from enum import Enum
from functools import wraps

from fastapi import HTTPException, Request

from .models import AuthContext, UserRole

logger = logging.getLogger(__name__)


# --- Role Hierarchy ---

# Higher roles inherit permissions from lower roles
ROLE_HIERARCHY = {
    UserRole.COMMANDER: 4,
    UserRole.LEADERSHIP: 3,
    UserRole.ANALYST: 2,
    UserRole.VIEWER: 1,
}


def role_level(role: UserRole) -> int:
    """Get numeric level for role comparison."""
    return ROLE_HIERARCHY.get(role, 0)


def role_includes(user_role: UserRole, required_role: UserRole) -> bool:
    """Check if user_role is at or above required_role in hierarchy."""
    return role_level(user_role) >= role_level(required_role)


# --- Permission Definitions ---


class Permission(str, Enum):
    """Granular permissions for resource access."""

    # Read permissions
    READ_DASHBOARD = "read:dashboard"
    READ_SIGNALS = "read:signals"
    READ_BRIEFS = "read:briefs"
    READ_BATTLEFIELD = "read:battlefield"
    READ_REPORTS = "read:reports"
    READ_AUDIT = "read:audit"
    READ_USERS = "read:users"

    # Write permissions
    WRITE_POSTURE = "write:posture"
    WRITE_TASKS = "write:tasks"
    WRITE_BRIEFS = "write:briefs"
    WRITE_BATTLEFIELD = "write:battlefield"

    # Export permissions
    EXPORT_REPORTS = "export:reports"
    EXPORT_DATA = "export:data"

    # Admin permissions
    MANAGE_USERS = "manage:users"
    MANAGE_ROLES = "manage:roles"
    VIEW_AUDIT = "view:audit"
    EXPORT_AUDIT = "export:audit"


# Role to permissions mapping
ROLE_PERMISSIONS: dict[UserRole, set[Permission]] = {
    UserRole.COMMANDER: {
        # Full access
        Permission.READ_DASHBOARD,
        Permission.READ_SIGNALS,
        Permission.READ_BRIEFS,
        Permission.READ_BATTLEFIELD,
        Permission.READ_REPORTS,
        Permission.READ_AUDIT,
        Permission.READ_USERS,
        Permission.WRITE_POSTURE,
        Permission.WRITE_TASKS,
        Permission.WRITE_BRIEFS,
        Permission.WRITE_BATTLEFIELD,
        Permission.EXPORT_REPORTS,
        Permission.EXPORT_DATA,
        Permission.MANAGE_USERS,
        Permission.MANAGE_ROLES,
        Permission.VIEW_AUDIT,
        Permission.EXPORT_AUDIT,
    },
    UserRole.LEADERSHIP: {
        # Read all, write posture/tasks, no user mgmt
        Permission.READ_DASHBOARD,
        Permission.READ_SIGNALS,
        Permission.READ_BRIEFS,
        Permission.READ_BATTLEFIELD,
        Permission.READ_REPORTS,
        Permission.WRITE_POSTURE,
        Permission.WRITE_TASKS,
        Permission.EXPORT_REPORTS,
    },
    UserRole.ANALYST: {
        # Read all, generate reports, no writes
        Permission.READ_DASHBOARD,
        Permission.READ_SIGNALS,
        Permission.READ_BRIEFS,
        Permission.READ_BATTLEFIELD,
        Permission.READ_REPORTS,
        Permission.EXPORT_REPORTS,
    },
    UserRole.VIEWER: {
        # Read dashboards only, no exports
        Permission.READ_DASHBOARD,
    },
}


def get_permissions_for_role(role: UserRole) -> set[Permission]:
    """Get all permissions for a role."""
    return ROLE_PERMISSIONS.get(role, set())


def get_permission_strings(role: UserRole) -> list[str]:
    """Get permissions as string list (for API responses)."""
    return [p.value for p in get_permissions_for_role(role)]


def has_permission(role: UserRole, permission: Permission) -> bool:
    """Check if role has a specific permission."""
    return permission in get_permissions_for_role(role)


def has_any_permission(role: UserRole, permissions: set[Permission]) -> bool:
    """Check if role has any of the specified permissions."""
    role_perms = get_permissions_for_role(role)
    return bool(role_perms & permissions)


def has_all_permissions(role: UserRole, permissions: set[Permission]) -> bool:
    """Check if role has all of the specified permissions."""
    role_perms = get_permissions_for_role(role)
    return permissions <= role_perms


# --- Access Control Decorators ---


def require_permission(*permissions: Permission):
    """
    Decorator factory requiring specific permissions.

    Usage:
        @router.get("/audit")
        @require_permission(Permission.VIEW_AUDIT)
        async def get_audit(user: AuthContext = Depends(require_auth)):
            ...
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Find AuthContext in kwargs
            user = kwargs.get("user") or kwargs.get("auth_context")
            if not user:
                # Try to find in args (shouldn't happen with proper DI)
                for arg in args:
                    if isinstance(arg, AuthContext):
                        user = arg
                        break

            if not user:
                raise HTTPException(
                    status_code=401,
                    detail="Authentication required",
                )

            # Check permissions
            required = set(permissions)
            if not has_all_permissions(user.role, required):
                missing = required - get_permissions_for_role(user.role)
                raise HTTPException(
                    status_code=403,
                    detail=f"Missing permissions: {[p.value for p in missing]}",
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def require_any_permission(*permissions: Permission):
    """
    Decorator factory requiring any of the specified permissions.
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            user = kwargs.get("user") or kwargs.get("auth_context")
            if not user:
                for arg in args:
                    if isinstance(arg, AuthContext):
                        user = arg
                        break

            if not user:
                raise HTTPException(status_code=401, detail="Authentication required")

            if not has_any_permission(user.role, set(permissions)):
                raise HTTPException(
                    status_code=403,
                    detail=f"Requires one of: {[p.value for p in permissions]}",
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def require_minimum_role(minimum_role: UserRole):
    """
    Decorator factory requiring minimum role level.

    Usage:
        @router.post("/tasks")
        @require_minimum_role(UserRole.LEADERSHIP)
        async def create_task(user: AuthContext = Depends(require_auth)):
            ...
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            user = kwargs.get("user") or kwargs.get("auth_context")
            if not user:
                for arg in args:
                    if isinstance(arg, AuthContext):
                        user = arg
                        break

            if not user:
                raise HTTPException(status_code=401, detail="Authentication required")

            if not role_includes(user.role, minimum_role):
                raise HTTPException(
                    status_code=403,
                    detail=f"Requires {minimum_role.value} or higher",
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


# --- Resource-Level Access Control ---


class ResourceAccess:
    """
    Helper class for checking resource-level access.

    Usage:
        access = ResourceAccess(user.role)
        if access.can_write("posture"):
            # allow posture update
    """

    def __init__(self, role: UserRole):
        self.role = role
        self.permissions = get_permissions_for_role(role)

    def can_read(self, resource: str) -> bool:
        """Check if user can read a resource type."""
        perm_name = f"read:{resource}"
        # Check exact match or "read:all" equivalent (commander)
        for p in self.permissions:
            if p.value == perm_name:
                return True
        return False

    def can_write(self, resource: str) -> bool:
        """Check if user can write to a resource type."""
        perm_name = f"write:{resource}"
        for p in self.permissions:
            if p.value == perm_name:
                return True
        return False

    def can_export(self, resource: str) -> bool:
        """Check if user can export a resource type."""
        perm_name = f"export:{resource}"
        for p in self.permissions:
            if p.value == perm_name:
                return True
        return False

    def can_manage(self, resource: str) -> bool:
        """Check if user can manage a resource type."""
        perm_name = f"manage:{resource}"
        for p in self.permissions:
            if p.value == perm_name:
                return True
        return False


def get_resource_access(user: AuthContext) -> ResourceAccess:
    """Create ResourceAccess helper for a user."""
    return ResourceAccess(user.role)


# --- FastAPI Dependencies ---


def PermissionChecker(*permissions: Permission):
    """
    FastAPI dependency factory for permission checking.

    Usage:
        @router.get("/audit")
        async def get_audit(
            user: AuthContext = Depends(require_auth),
            _: None = Depends(PermissionChecker(Permission.VIEW_AUDIT))
        ):
            ...
    """

    async def check_permissions(request: Request):
        from .middleware import get_current_user

        user = get_current_user(request)
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")

        required = set(permissions)
        if not has_all_permissions(user.role, required):
            missing = required - get_permissions_for_role(user.role)
            raise HTTPException(
                status_code=403,
                detail=f"Missing permissions: {[p.value for p in missing]}",
            )
        return None

    return check_permissions


def RoleChecker(minimum_role: UserRole):
    """
    FastAPI dependency factory for role level checking.

    Usage:
        @router.post("/command")
        async def issue_command(
            user: AuthContext = Depends(require_auth),
            _: None = Depends(RoleChecker(UserRole.COMMANDER))
        ):
            ...
    """

    async def check_role(request: Request):
        from .middleware import get_current_user

        user = get_current_user(request)
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")

        if not role_includes(user.role, minimum_role):
            raise HTTPException(
                status_code=403,
                detail=f"Requires {minimum_role.value} or higher",
            )
        return None

    return check_role
