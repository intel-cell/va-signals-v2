"""
Integration Verification Tests

HOTEL COMMAND - Phase 1 Integration Verification
Verifies ECHO auth module is properly integrated with dashboard_api.

These tests confirm the integration is working before full test suite execution.
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
import time


@pytest.fixture
def app_client():
    """Create test client with mocked Firebase init."""
    with patch('src.auth.firebase_config.init_firebase'):
        from src.dashboard_api import app
        return TestClient(app)


@pytest.fixture
def mock_firebase_claims():
    """Standard mock claims for testing."""
    now = int(time.time())
    return {
        'user_id': 'test-uid-001',
        'email': 'test@veteran-signals.com',
        'display_name': 'Test User',
        'iat': now,
        'exp': now + 3600,
    }


class TestAuthModuleIntegration:
    """Verify ECHO auth module is integrated."""

    def test_auth_router_mounted(self, app_client):
        """Verify auth router is mounted at /api/auth."""
        # CSRF endpoint should be accessible
        response = app_client.get("/api/auth/csrf")
        assert response.status_code == 200
        data = response.json()
        assert "csrf_token" in data

    def test_auth_endpoints_exist(self, app_client):
        """Verify all auth endpoints exist."""
        # These should return 401 (requires auth) or other codes, not 404
        endpoints = [
            ("/api/auth/login", "POST"),
            ("/api/auth/verify", "POST"),
            ("/api/auth/logout", "POST"),
            ("/api/auth/me", "GET"),
            ("/api/auth/users", "GET"),
        ]

        for path, method in endpoints:
            if method == "GET":
                response = app_client.get(path)
            else:
                response = app_client.post(path, json={})

            # Should not be 404 (endpoint exists)
            assert response.status_code != 404, f"{method} {path} returned 404"

    def test_csrf_endpoint_public(self, app_client):
        """Verify CSRF endpoint is public (no auth required)."""
        response = app_client.get("/api/auth/csrf")
        assert response.status_code == 200
        data = response.json()
        assert "csrf_token" in data


class TestAuthMiddleware:
    """Verify auth middleware is functioning."""

    def test_unauthenticated_protected_endpoint_returns_401(self, app_client):
        """Protected endpoints should return 401 without auth."""
        # /api/auth/me requires authentication
        response = app_client.get("/api/auth/me")
        assert response.status_code == 401

    def test_bearer_token_triggers_auth_check(self, app_client):
        """Verify Bearer token triggers authentication check."""
        # Without valid Firebase setup, requests with Bearer token
        # should still go through auth middleware (returns 401 if token invalid)
        response = app_client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer any-token"}
        )

        # Should be 401 (invalid token) not 404 or 500
        # This proves the auth middleware is processing the token
        assert response.status_code == 401

    def test_invalid_token_returns_401(self, app_client):
        """Invalid tokens should return 401."""
        with patch('src.auth.firebase_config.verify_firebase_token') as mock_verify:
            mock_verify.return_value = None  # Invalid token

            response = app_client.get(
                "/api/auth/me",
                headers={"Authorization": "Bearer invalid-token"}
            )

            assert response.status_code == 401


class TestCSRFProtection:
    """Verify CSRF protection is active."""

    def test_csrf_token_endpoint_works(self, app_client):
        """CSRF endpoint should return valid token."""
        response = app_client.get("/api/auth/csrf")
        assert response.status_code == 200

        data = response.json()
        assert "csrf_token" in data
        assert len(data["csrf_token"]) > 20  # Should be substantial token


class TestRBACIntegration:
    """Verify RBAC components are available."""

    def test_rbac_imports_available(self):
        """Verify RBAC can be imported from auth module."""
        from src.auth import (
            require_auth,
            require_role,
            UserRole,
            Permission,
            has_permission,
            require_permission,
        )

        # Verify UserRole enum has expected values
        assert UserRole.COMMANDER.value == "commander"
        assert UserRole.LEADERSHIP.value == "leadership"
        assert UserRole.ANALYST.value == "analyst"
        assert UserRole.VIEWER.value == "viewer"

    def test_permission_enum_exists(self):
        """Verify Permission enum has expected values."""
        from src.auth import Permission

        # Check some expected permissions exist
        assert hasattr(Permission, 'READ_DASHBOARD')
        assert hasattr(Permission, 'MANAGE_USERS')


class TestAuditIntegration:
    """Verify audit logging components are available."""

    def test_audit_imports_available(self):
        """Verify audit can be imported from auth module."""
        from src.auth import (
            AuditMiddleware,
            log_audit,
            get_audit_logs,
            get_audit_stats,
        )

        # Should not raise import errors
        assert AuditMiddleware is not None
        assert callable(log_audit)


class TestDashboardAPIIntegration:
    """Verify dashboard_api has auth integrated."""

    def test_dashboard_api_includes_auth_router(self):
        """Verify dashboard_api includes auth router."""
        from src.dashboard_api import app

        # Check that auth routes are in the app
        routes = [route.path for route in app.routes if hasattr(route, 'path')]
        auth_routes = [r for r in routes if r.startswith('/api/auth')]

        assert len(auth_routes) > 0, "No auth routes found in app"
        assert '/api/auth/login' in routes or any('/api/auth' in r for r in routes)

    def test_existing_endpoints_still_work(self, app_client, mock_firebase_claims):
        """Verify existing dashboard endpoints still function with RBAC."""
        from src.auth.models import AuthContext, UserRole

        # Create mock auth context for RBAC validation
        mock_auth = AuthContext(
            user_id=mock_firebase_claims["user_id"],
            email=mock_firebase_claims["email"],
            role=UserRole.VIEWER,  # Minimum role needed for /api/runs/stats
            display_name=mock_firebase_claims.get("display_name"),
            auth_method="firebase",
        )

        # Patch get_current_user at the middleware module level
        with patch('src.auth.middleware.get_current_user', return_value=mock_auth):
            # Test existing endpoint with auth
            response = app_client.get(
                "/api/runs/stats",
                headers={"Authorization": "Bearer mock-token"}
            )

            assert response.status_code == 200
            data = response.json()
            assert "total_runs" in data
