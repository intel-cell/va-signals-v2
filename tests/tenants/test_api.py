"""Tests for tenant API endpoints.

The tenant router is not yet mounted in the main dashboard app, so these tests
create a standalone FastAPI app with the tenant router mounted. Auth dependencies
are overridden via FastAPI dependency_overrides to inject AuthContext.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.auth.middleware import require_auth
from src.auth.models import AuthContext, UserRole
from src.tenants.api import router as tenant_router


def _auth_context(role: UserRole, user_id: str = "test-uid") -> AuthContext:
    return AuthContext(
        user_id=user_id,
        email=f"{role.value}@test.com",
        role=role,
        display_name=f"Test {role.value.title()}",
        auth_method="firebase",
    )


def _make_app(auth_ctx: AuthContext | None = None):
    """Create a minimal FastAPI app with tenant router and auth overrides."""
    app = FastAPI()
    app.include_router(tenant_router)

    if auth_ctx is not None:
        # Override require_auth to return the given context
        app.dependency_overrides[require_auth] = lambda: auth_ctx

    return app


def _client_with_auth(role: UserRole, user_id: str = "test-uid"):
    """Return a TestClient with auth overridden for the given role."""
    ctx = _auth_context(role, user_id=user_id)
    app = _make_app(ctx)
    return TestClient(app, raise_server_exceptions=False), ctx


def _seed_user(uid, email, name, role):
    """Insert a user row into the test DB."""
    from src.db import connect, execute

    con = connect()
    execute(
        con,
        "INSERT OR IGNORE INTO users (user_id, email, display_name, role, created_at) "
        "VALUES (:uid, :email, :name, :role, :ts)",
        {"uid": uid, "email": email, "name": name, "role": role, "ts": "2024-01-01"},
    )
    con.commit()
    con.close()


# ---------------------------------------------------------------------------
# POST /api/tenants — create tenant
# ---------------------------------------------------------------------------


class TestCreateTenantEndpoint:
    def test_create_tenant_as_commander(self):
        client, _ = _client_with_auth(UserRole.COMMANDER, user_id="cmd-001")
        _seed_user("cmd-001", "commander@test.com", "Commander", "commander")
        response = client.post(
            "/api/tenants",
            json={"name": "New Org", "slug": "new-org", "plan": "starter"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "New Org"
        assert body["slug"] == "new-org"
        assert body["plan"] == "starter"
        assert body["member_count"] == 1

    def test_create_tenant_as_viewer(self):
        """Any authenticated user can create a tenant (they become the owner)."""
        client, _ = _client_with_auth(UserRole.VIEWER, user_id="viewer-001")
        _seed_user("viewer-001", "viewer@test.com", "Viewer", "viewer")
        response = client.post(
            "/api/tenants",
            json={"name": "Viewer Org", "slug": "viewer-org"},
        )
        assert response.status_code == 200

    def test_create_duplicate_slug_fails(self):
        client, _ = _client_with_auth(UserRole.COMMANDER, user_id="dup-001")
        _seed_user("dup-001", "dup@test.com", "Dup", "commander")
        client.post(
            "/api/tenants",
            json={"name": "First", "slug": "dup-slug"},
        )
        response = client.post(
            "/api/tenants",
            json={"name": "Second", "slug": "dup-slug"},
        )
        assert response.status_code == 500


# ---------------------------------------------------------------------------
# GET /api/tenants/me — list user's tenants
# ---------------------------------------------------------------------------


class TestGetMyTenantsEndpoint:
    def test_returns_user_tenants(self):
        client, _ = _client_with_auth(UserRole.COMMANDER, user_id="me-001")
        _seed_user("me-001", "me@test.com", "Me", "commander")
        # Create a tenant first
        client.post(
            "/api/tenants",
            json={"name": "My Org", "slug": "my-org-me"},
        )
        response = client.get("/api/tenants/me")
        assert response.status_code == 200
        body = response.json()
        assert body["count"] >= 1

    def test_empty_tenants(self):
        client, _ = _client_with_auth(UserRole.VIEWER, user_id="lonely-001")
        response = client.get("/api/tenants/me")
        assert response.status_code == 200
        assert response.json()["count"] == 0


# ---------------------------------------------------------------------------
# GET /api/tenants/current — requires tenant context
# ---------------------------------------------------------------------------


class TestGetCurrentTenantEndpoint:
    def test_no_tenant_context_returns_400(self):
        client, _ = _client_with_auth(UserRole.VIEWER)
        response = client.get("/api/tenants/current")
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/tenants/{tenant_id} — requires VIEWER via RoleChecker
# ---------------------------------------------------------------------------


class TestGetTenantEndpoint:
    def test_viewer_can_access(self):
        ctx = _auth_context(UserRole.VIEWER)
        app = _make_app(ctx)
        # RoleChecker uses get_current_user(request) which reads request.state
        # We need middleware to set it. Use dependency_overrides for RoleChecker.
        # The endpoint uses Depends(RoleChecker(UserRole.VIEWER)) — but RoleChecker
        # returns a new function each call, so we can't override it directly.
        # Instead, inject auth_context via middleware.
        from starlette.middleware.base import BaseHTTPMiddleware

        class InjectAuth(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                request.state.auth_context = ctx
                return await call_next(request)

        app.add_middleware(InjectAuth)
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/tenants/tenant_nonexistent")
        assert response.status_code == 404

    def test_unauthenticated_returns_401(self):
        app = _make_app()  # No auth override
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/tenants/tenant_abc")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/tenants/{tenant_id}/settings — requires LEADERSHIP
# ---------------------------------------------------------------------------


def _client_with_role_middleware(role: UserRole):
    """Create a client with auth injected via middleware (for RoleChecker endpoints)."""
    from starlette.middleware.base import BaseHTTPMiddleware

    ctx = _auth_context(role)
    app = _make_app(ctx)

    class InjectAuth(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            request.state.auth_context = ctx
            return await call_next(request)

    app.add_middleware(InjectAuth)
    return TestClient(app, raise_server_exceptions=False)


class TestGetTenantSettingsEndpoint:
    def test_viewer_cannot_access(self):
        client = _client_with_role_middleware(UserRole.VIEWER)
        response = client.get("/api/tenants/tenant_abc/settings")
        assert response.status_code == 403

    def test_analyst_cannot_access(self):
        client = _client_with_role_middleware(UserRole.ANALYST)
        response = client.get("/api/tenants/tenant_abc/settings")
        assert response.status_code == 403

    def test_leadership_can_access(self):
        client = _client_with_role_middleware(UserRole.LEADERSHIP)
        response = client.get("/api/tenants/tenant_abc/settings")
        # RBAC passes -> 404 because tenant_abc doesn't exist
        assert response.status_code == 404

    def test_commander_can_access(self):
        client = _client_with_role_middleware(UserRole.COMMANDER)
        response = client.get("/api/tenants/tenant_abc/settings")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/tenants/{tenant_id}/members — requires ANALYST
# ---------------------------------------------------------------------------


class TestListMembersEndpoint:
    def test_viewer_cannot_list(self):
        client = _client_with_role_middleware(UserRole.VIEWER)
        response = client.get("/api/tenants/tenant_abc/members")
        assert response.status_code == 403

    def test_analyst_can_list(self):
        client = _client_with_role_middleware(UserRole.ANALYST)
        response = client.get("/api/tenants/tenant_abc/members")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# POST /api/tenants/{tenant_id}/members — invite, requires LEADERSHIP/COMMANDER
# ---------------------------------------------------------------------------


class TestInviteMemberEndpoint:
    def test_analyst_cannot_invite(self):
        client = _client_with_role_middleware(UserRole.ANALYST)
        response = client.post(
            "/api/tenants/tenant_abc/members",
            json={"email": "new@test.com", "role": "viewer"},
        )
        assert response.status_code == 403

    def test_viewer_cannot_invite(self):
        client = _client_with_role_middleware(UserRole.VIEWER)
        response = client.post(
            "/api/tenants/tenant_abc/members",
            json={"email": "new@test.com", "role": "viewer"},
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /api/tenants/{tenant_id}/members/{user_id} — requires COMMANDER
# ---------------------------------------------------------------------------


class TestRemoveMemberEndpoint:
    def test_viewer_cannot_remove(self):
        client = _client_with_role_middleware(UserRole.VIEWER)
        response = client.delete("/api/tenants/tenant_abc/members/user-001")
        assert response.status_code == 403

    def test_leadership_cannot_remove(self):
        client = _client_with_role_middleware(UserRole.LEADERSHIP)
        response = client.delete("/api/tenants/tenant_abc/members/user-001")
        assert response.status_code == 403

    def test_commander_can_remove(self):
        client = _client_with_role_middleware(UserRole.COMMANDER)
        response = client.delete("/api/tenants/tenant_abc/members/user-001")
        # RBAC passes; 400 because member doesn't exist
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# PATCH /api/tenants/{tenant_id}/members/{user_id}/role — requires COMMANDER
# ---------------------------------------------------------------------------


class TestUpdateMemberRoleEndpoint:
    def test_analyst_cannot_update_role(self):
        client = _client_with_role_middleware(UserRole.ANALYST)
        response = client.patch(
            "/api/tenants/tenant_abc/members/user-001/role?role=analyst",
        )
        assert response.status_code == 403

    def test_commander_can_update_role(self):
        client = _client_with_role_middleware(UserRole.COMMANDER)
        response = client.patch(
            "/api/tenants/tenant_abc/members/user-001/role?role=analyst",
        )
        # RBAC passes; 404 because member doesn't exist
        assert response.status_code == 404

    def test_invalid_role_returns_400(self):
        client = _client_with_role_middleware(UserRole.COMMANDER)
        response = client.patch(
            "/api/tenants/tenant_abc/members/user-001/role?role=superadmin",
        )
        assert response.status_code == 400
