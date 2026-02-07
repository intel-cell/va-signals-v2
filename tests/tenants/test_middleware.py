"""Tests for tenant middleware — context vars, query scoping, and resolution.

Tests the helper functions directly and the TenantMiddleware dispatch logic
using FastAPI TestClient.
"""

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from src.tenants.middleware import (
    TenantMiddleware,
    get_tenant_context,
    require_tenant_context,
    set_tenant_context,
    tenant_scoped_query,
)
from src.tenants.models import TenantContext, TenantPlan

# ---------------------------------------------------------------------------
# Context variable helpers
# ---------------------------------------------------------------------------


class TestGetSetTenantContext:
    def test_default_is_none(self):
        assert get_tenant_context() is None

    def test_set_and_get_roundtrip(self):
        ctx = TenantContext(
            tenant_id="t-1",
            tenant_name="Ctx Org",
            tenant_slug="ctx-org",
            plan=TenantPlan.FREE,
            user_id="u-1",
            user_role="viewer",
        )
        set_tenant_context(ctx)
        result = get_tenant_context()
        assert result is not None
        assert result.tenant_id == "t-1"
        # Cleanup
        set_tenant_context(None)

    def test_set_none_clears(self):
        ctx = TenantContext(
            tenant_id="t-1",
            tenant_name="Ctx Org",
            tenant_slug="ctx-org",
            plan=TenantPlan.FREE,
            user_id="u-1",
            user_role="viewer",
        )
        set_tenant_context(ctx)
        set_tenant_context(None)
        assert get_tenant_context() is None


class TestRequireTenantContext:
    def test_raises_when_no_context(self):
        set_tenant_context(None)
        with pytest.raises(HTTPException) as exc_info:
            require_tenant_context()
        assert exc_info.value.status_code == 400
        assert "Tenant context required" in exc_info.value.detail

    def test_returns_context_when_set(self):
        ctx = TenantContext(
            tenant_id="t-1",
            tenant_name="Ctx Org",
            tenant_slug="ctx-org",
            plan=TenantPlan.FREE,
            user_id="u-1",
            user_role="viewer",
        )
        set_tenant_context(ctx)
        result = require_tenant_context()
        assert result.tenant_id == "t-1"
        set_tenant_context(None)


# ---------------------------------------------------------------------------
# tenant_scoped_query
# ---------------------------------------------------------------------------


class TestTenantScopedQuery:
    def test_adds_and_clause_when_where_present(self):
        base = "SELECT * FROM signals WHERE severity = :severity"
        scoped = tenant_scoped_query(base, "t-1")
        assert scoped.endswith("AND tenant_id = :tenant_id")
        assert "WHERE severity" in scoped

    def test_adds_where_clause_when_none(self):
        base = "SELECT * FROM signals"
        scoped = tenant_scoped_query(base, "t-1")
        assert "WHERE tenant_id = :tenant_id" in scoped

    def test_custom_tenant_column(self):
        base = "SELECT * FROM events"
        scoped = tenant_scoped_query(base, "t-1", tenant_column="org_id")
        assert "WHERE org_id = :tenant_id" in scoped

    def test_case_insensitive_where_detection(self):
        base = "SELECT * FROM signals where active = 1"
        scoped = tenant_scoped_query(base, "t-1")
        assert "AND tenant_id = :tenant_id" in scoped


# ---------------------------------------------------------------------------
# TenantMiddleware — PUBLIC_PATHS and PUBLIC_PREFIXES
# ---------------------------------------------------------------------------


class TestMiddlewarePublicPaths:
    def test_health_is_public(self):
        assert "/health" in TenantMiddleware.PUBLIC_PATHS

    def test_docs_is_public(self):
        assert "/docs" in TenantMiddleware.PUBLIC_PATHS

    def test_auth_login_is_public(self):
        assert "/api/auth/login" in TenantMiddleware.PUBLIC_PATHS

    def test_static_prefix_is_public(self):
        assert "/static/".startswith(TenantMiddleware.PUBLIC_PREFIXES)

    def test_ws_prefix_is_public(self):
        assert "/ws/".startswith(TenantMiddleware.PUBLIC_PREFIXES)


# ---------------------------------------------------------------------------
# TenantMiddleware — dispatch integration via test app
# ---------------------------------------------------------------------------


def _make_test_app():
    """Create a minimal FastAPI app with TenantMiddleware for integration tests."""
    app = FastAPI()

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/data")
    async def data():
        return {"data": "value"}

    app.add_middleware(TenantMiddleware)
    return app


class TestMiddlewareDispatch:
    def test_public_path_bypasses_tenant(self):
        app = _make_test_app()
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200

    def test_no_user_id_skips_resolution(self):
        """When no user is authenticated, middleware skips tenant resolution."""
        app = _make_test_app()
        client = TestClient(app)
        response = client.get("/api/data")
        # No auth state set, so middleware skips resolution and proceeds
        assert response.status_code == 200


class TestResolveTenantWithHeaders:
    """Test _resolve_tenant logic via X-Tenant-ID and X-Tenant-Slug headers.

    These tests use a real tenant in the test DB. They verify the middleware
    resolves tenant context correctly from request headers.
    """

    def test_resolve_by_tenant_id_header(self, manager, created_tenant, _seed_owner_user):
        """Middleware should resolve tenant from X-Tenant-ID header."""
        app = FastAPI()

        @app.get("/api/test")
        async def endpoint(request: Request):
            ctx = get_tenant_context()
            if ctx:
                return {"tenant_id": ctx.tenant_id, "role": ctx.user_role}
            return {"tenant_id": None}

        app.add_middleware(TenantMiddleware)

        # We need to inject user_id into request.state before TenantMiddleware runs.
        # Add a shim middleware that runs first (added last = runs first in Starlette).
        class InjectUser(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                request.state.user_id = "owner-001"
                request.state.user_email = "owner@test.com"
                return await call_next(request)

        app.add_middleware(InjectUser)

        client = TestClient(app)
        response = client.get(
            "/api/test",
            headers={"X-Tenant-ID": created_tenant.tenant_id},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["tenant_id"] == created_tenant.tenant_id
        assert body["role"] == "commander"

    def test_resolve_by_tenant_slug_header(self, manager, created_tenant, _seed_owner_user):
        """Middleware should resolve tenant from X-Tenant-Slug header."""
        app = FastAPI()

        @app.get("/api/test")
        async def endpoint(request: Request):
            ctx = get_tenant_context()
            if ctx:
                return {"tenant_id": ctx.tenant_id}
            return {"tenant_id": None}

        app.add_middleware(TenantMiddleware)

        class InjectUser(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                request.state.user_id = "owner-001"
                request.state.user_email = "owner@test.com"
                return await call_next(request)

        app.add_middleware(InjectUser)

        client = TestClient(app)
        response = client.get(
            "/api/test",
            headers={"X-Tenant-Slug": "test-org"},
        )
        assert response.status_code == 200
        assert response.json()["tenant_id"] == created_tenant.tenant_id

    def test_resolve_fallback_to_primary(self, manager, created_tenant, _seed_owner_user):
        """When no tenant header, middleware falls back to user's primary tenant."""
        app = FastAPI()

        @app.get("/api/test")
        async def endpoint(request: Request):
            ctx = get_tenant_context()
            if ctx:
                return {"tenant_id": ctx.tenant_id}
            return {"tenant_id": None}

        app.add_middleware(TenantMiddleware)

        class InjectUser(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                request.state.user_id = "owner-001"
                request.state.user_email = "owner@test.com"
                return await call_next(request)

        app.add_middleware(InjectUser)

        client = TestClient(app)
        response = client.get("/api/test")
        assert response.status_code == 200
        assert response.json()["tenant_id"] == created_tenant.tenant_id

    def test_non_member_gets_403(
        self, manager, created_tenant, _seed_owner_user, _seed_extra_users
    ):
        """Non-member access to a tenant should raise 403."""
        app = FastAPI()

        @app.get("/api/test")
        async def endpoint():
            return {"ok": True}

        app.add_middleware(TenantMiddleware)

        class InjectUser(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                request.state.user_id = "user-002"  # Not a member of created_tenant
                request.state.user_email = "member2@test.com"
                return await call_next(request)

        app.add_middleware(InjectUser)

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/api/test",
            headers={"X-Tenant-ID": created_tenant.tenant_id},
        )
        assert response.status_code == 403

    def test_resolve_by_subdomain(self, manager, created_tenant, _seed_owner_user):
        """Middleware should resolve tenant from subdomain."""
        app = FastAPI()

        @app.get("/api/test")
        async def endpoint(request: Request):
            ctx = get_tenant_context()
            if ctx:
                return {"tenant_id": ctx.tenant_id}
            return {"tenant_id": None}

        app.add_middleware(TenantMiddleware)

        class InjectUser(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                request.state.user_id = "owner-001"
                request.state.user_email = "owner@test.com"
                return await call_next(request)

        app.add_middleware(InjectUser)

        client = TestClient(app)
        response = client.get(
            "/api/test",
            headers={"host": "test-org.vasignals.com"},
        )
        assert response.status_code == 200
        assert response.json()["tenant_id"] == created_tenant.tenant_id

    def test_context_cleared_after_request(self, manager, created_tenant, _seed_owner_user):
        """Tenant context should be cleared after each request."""
        app = FastAPI()

        @app.get("/api/test")
        async def endpoint(request: Request):
            ctx = get_tenant_context()
            return {"has_context": ctx is not None}

        app.add_middleware(TenantMiddleware)

        class InjectUser(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                request.state.user_id = "owner-001"
                request.state.user_email = "owner@test.com"
                return await call_next(request)

        app.add_middleware(InjectUser)

        client = TestClient(app)
        client.get(
            "/api/test",
            headers={"X-Tenant-ID": created_tenant.tenant_id},
        )
        # After request completes, context should be None
        assert get_tenant_context() is None
