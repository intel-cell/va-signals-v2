"""
RBAC Unit Tests

Tests role hierarchy, permission checks, and resource access helpers
at the function level — no HTTP client or FastAPI dependency needed.
"""

import pytest

from src.auth.models import AuthContext, UserRole
from src.auth.rbac import (
    ROLE_HIERARCHY,
    ROLE_PERMISSIONS,
    Permission,
    ResourceAccess,
    get_permission_strings,
    get_permissions_for_role,
    get_resource_access,
    has_all_permissions,
    has_any_permission,
    has_permission,
    role_includes,
    role_level,
)

# ---------------------------------------------------------------------------
# role_level
# ---------------------------------------------------------------------------


class TestRoleLevel:
    def test_commander_level(self):
        assert role_level(UserRole.COMMANDER) == 4

    def test_leadership_level(self):
        assert role_level(UserRole.LEADERSHIP) == 3

    def test_analyst_level(self):
        assert role_level(UserRole.ANALYST) == 2

    def test_viewer_level(self):
        assert role_level(UserRole.VIEWER) == 1


# ---------------------------------------------------------------------------
# role_includes  (4x4 = 16 parametrized cases)
# ---------------------------------------------------------------------------


class TestRoleIncludes:
    @pytest.mark.parametrize(
        "user_role,required_role,expected",
        [
            # COMMANDER includes all
            (UserRole.COMMANDER, UserRole.COMMANDER, True),
            (UserRole.COMMANDER, UserRole.LEADERSHIP, True),
            (UserRole.COMMANDER, UserRole.ANALYST, True),
            (UserRole.COMMANDER, UserRole.VIEWER, True),
            # LEADERSHIP includes self and below
            (UserRole.LEADERSHIP, UserRole.COMMANDER, False),
            (UserRole.LEADERSHIP, UserRole.LEADERSHIP, True),
            (UserRole.LEADERSHIP, UserRole.ANALYST, True),
            (UserRole.LEADERSHIP, UserRole.VIEWER, True),
            # ANALYST includes self and below
            (UserRole.ANALYST, UserRole.COMMANDER, False),
            (UserRole.ANALYST, UserRole.LEADERSHIP, False),
            (UserRole.ANALYST, UserRole.ANALYST, True),
            (UserRole.ANALYST, UserRole.VIEWER, True),
            # VIEWER includes only self
            (UserRole.VIEWER, UserRole.COMMANDER, False),
            (UserRole.VIEWER, UserRole.LEADERSHIP, False),
            (UserRole.VIEWER, UserRole.ANALYST, False),
            (UserRole.VIEWER, UserRole.VIEWER, True),
        ],
    )
    def test_role_includes(self, user_role, required_role, expected):
        assert role_includes(user_role, required_role) == expected


# ---------------------------------------------------------------------------
# has_permission
# ---------------------------------------------------------------------------


class TestHasPermission:
    def test_commander_has_manage_users(self):
        assert has_permission(UserRole.COMMANDER, Permission.MANAGE_USERS) is True

    def test_viewer_lacks_manage_users(self):
        assert has_permission(UserRole.VIEWER, Permission.MANAGE_USERS) is False

    def test_analyst_has_read_signals(self):
        assert has_permission(UserRole.ANALYST, Permission.READ_SIGNALS) is True

    def test_viewer_has_read_dashboard(self):
        assert has_permission(UserRole.VIEWER, Permission.READ_DASHBOARD) is True

    def test_viewer_lacks_read_signals(self):
        assert has_permission(UserRole.VIEWER, Permission.READ_SIGNALS) is False

    def test_leadership_has_write_posture(self):
        assert has_permission(UserRole.LEADERSHIP, Permission.WRITE_POSTURE) is True

    def test_analyst_lacks_write_posture(self):
        assert has_permission(UserRole.ANALYST, Permission.WRITE_POSTURE) is False

    def test_commander_has_export_audit(self):
        assert has_permission(UserRole.COMMANDER, Permission.EXPORT_AUDIT) is True

    def test_leadership_lacks_manage_roles(self):
        assert has_permission(UserRole.LEADERSHIP, Permission.MANAGE_ROLES) is False


# ---------------------------------------------------------------------------
# has_any_permission / has_all_permissions
# ---------------------------------------------------------------------------


class TestPermissionCombinations:
    def test_viewer_has_any_dashboard_or_signals(self):
        assert (
            has_any_permission(
                UserRole.VIEWER,
                {Permission.READ_DASHBOARD, Permission.READ_SIGNALS},
            )
            is True
        )

    def test_viewer_has_none_of_admin_set(self):
        assert (
            has_any_permission(
                UserRole.VIEWER,
                {Permission.MANAGE_USERS, Permission.WRITE_POSTURE},
            )
            is False
        )

    def test_commander_has_all_admin(self):
        assert (
            has_all_permissions(
                UserRole.COMMANDER,
                {Permission.MANAGE_USERS, Permission.MANAGE_ROLES},
            )
            is True
        )

    def test_analyst_lacks_all_signals_and_manage(self):
        assert (
            has_all_permissions(
                UserRole.ANALYST,
                {Permission.READ_SIGNALS, Permission.MANAGE_USERS},
            )
            is False
        )

    def test_leadership_has_all_read_write_posture(self):
        assert (
            has_all_permissions(
                UserRole.LEADERSHIP,
                {Permission.READ_DASHBOARD, Permission.WRITE_POSTURE},
            )
            is True
        )

    def test_has_any_empty_set(self):
        # Empty intersection is falsy
        assert has_any_permission(UserRole.VIEWER, set()) is False

    def test_has_all_empty_set(self):
        # Empty set is subset of everything
        assert has_all_permissions(UserRole.VIEWER, set()) is True


# ---------------------------------------------------------------------------
# get_permissions_for_role / get_permission_strings
# ---------------------------------------------------------------------------


class TestPermissionRetrieval:
    def test_commander_has_all_17_permissions(self):
        perms = get_permissions_for_role(UserRole.COMMANDER)
        assert len(perms) == 17

    def test_viewer_has_1_permission(self):
        perms = get_permissions_for_role(UserRole.VIEWER)
        assert len(perms) == 1

    def test_analyst_has_6_permissions(self):
        perms = get_permissions_for_role(UserRole.ANALYST)
        assert len(perms) == 6

    def test_leadership_has_8_permissions(self):
        perms = get_permissions_for_role(UserRole.LEADERSHIP)
        assert len(perms) == 8

    def test_permission_strings_returns_list(self):
        strings = get_permission_strings(UserRole.VIEWER)
        assert isinstance(strings, list)
        assert "read:dashboard" in strings

    def test_commander_permission_strings_complete(self):
        strings = get_permission_strings(UserRole.COMMANDER)
        assert len(strings) == 17
        assert "manage:users" in strings
        assert "manage:roles" in strings


# ---------------------------------------------------------------------------
# ResourceAccess
# ---------------------------------------------------------------------------


class TestResourceAccess:
    def test_commander_can_read_dashboard(self):
        assert ResourceAccess(UserRole.COMMANDER).can_read("dashboard") is True

    def test_commander_can_write_posture(self):
        assert ResourceAccess(UserRole.COMMANDER).can_write("posture") is True

    def test_commander_can_export_reports(self):
        assert ResourceAccess(UserRole.COMMANDER).can_export("reports") is True

    def test_commander_can_manage_users(self):
        assert ResourceAccess(UserRole.COMMANDER).can_manage("users") is True

    def test_viewer_can_read_dashboard(self):
        assert ResourceAccess(UserRole.VIEWER).can_read("dashboard") is True

    def test_viewer_cannot_write_posture(self):
        assert ResourceAccess(UserRole.VIEWER).can_write("posture") is False

    def test_viewer_cannot_export_reports(self):
        assert ResourceAccess(UserRole.VIEWER).can_export("reports") is False

    def test_viewer_cannot_manage_users(self):
        assert ResourceAccess(UserRole.VIEWER).can_manage("users") is False

    def test_analyst_can_read_signals(self):
        assert ResourceAccess(UserRole.ANALYST).can_read("signals") is True

    def test_analyst_cannot_write_posture(self):
        assert ResourceAccess(UserRole.ANALYST).can_write("posture") is False

    def test_analyst_can_export_reports(self):
        assert ResourceAccess(UserRole.ANALYST).can_export("reports") is True

    def test_leadership_can_write_tasks(self):
        assert ResourceAccess(UserRole.LEADERSHIP).can_write("tasks") is True

    def test_nonexistent_resource_returns_false(self):
        assert ResourceAccess(UserRole.COMMANDER).can_read("nonexistent") is False


# ---------------------------------------------------------------------------
# get_resource_access
# ---------------------------------------------------------------------------


class TestGetResourceAccess:
    def test_returns_resource_access_instance(self):
        ctx = AuthContext(
            user_id="u1",
            email="a@b.com",
            role=UserRole.ANALYST,
            auth_method="firebase",
        )
        ra = get_resource_access(ctx)
        assert isinstance(ra, ResourceAccess)
        assert ra.role == UserRole.ANALYST

    def test_resource_access_reflects_role(self):
        ctx = AuthContext(
            user_id="u2",
            email="c@d.com",
            role=UserRole.COMMANDER,
            auth_method="firebase",
        )
        ra = get_resource_access(ctx)
        assert ra.can_manage("users") is True


# ---------------------------------------------------------------------------
# Constants sanity
# ---------------------------------------------------------------------------


class TestConstants:
    def test_role_hierarchy_has_four_roles(self):
        assert len(ROLE_HIERARCHY) == 4

    def test_role_permissions_has_four_roles(self):
        assert len(ROLE_PERMISSIONS) == 4

    def test_permission_enum_has_17_members(self):
        assert len(Permission) == 17

    def test_commander_permissions_superset_of_all(self):
        cmd_perms = ROLE_PERMISSIONS[UserRole.COMMANDER]
        for role, perms in ROLE_PERMISSIONS.items():
            assert perms <= cmd_perms, f"{role} has permissions not in COMMANDER"
