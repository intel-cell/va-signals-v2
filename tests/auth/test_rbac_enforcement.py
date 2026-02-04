"""
RBAC Enforcement Tests

HOTEL COMMAND - Phase 1 Integration
Verifies role-based access control is properly enforced across all protected endpoints.

Tests:
- Unauthenticated requests return 401
- Insufficient role returns 403
- Sufficient role returns 200
- Role hierarchy is respected
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from src.auth.models import AuthContext, UserRole


@pytest.fixture
def app_client():
    """Create test client with mocked Firebase init."""
    with patch('src.auth.firebase_config.init_firebase'):
        from src.dashboard_api import app
        return TestClient(app)


def make_auth_context(role: UserRole) -> AuthContext:
    """Create mock AuthContext for testing."""
    return AuthContext(
        user_id=f"test-{role.value}-uid",
        email=f"{role.value}@veteran-signals.com",
        role=role,
        display_name=f"Test {role.value.title()}",
        auth_method="firebase",
    )


class TestUnauthenticatedAccess:
    """Verify unauthenticated requests are rejected."""

    def test_viewer_endpoint_requires_auth(self, app_client):
        """VIEWER endpoints should require authentication."""
        response = app_client.get("/api/runs/stats")
        assert response.status_code == 401

    def test_analyst_endpoint_requires_auth(self, app_client):
        """ANALYST endpoints should require authentication."""
        response = app_client.get("/api/runs")
        assert response.status_code == 401

    def test_leadership_endpoint_requires_auth(self, app_client):
        """LEADERSHIP endpoints should require authentication."""
        response = app_client.post("/api/battlefield/sync")
        assert response.status_code == 401

    def test_commander_endpoint_requires_auth(self, app_client):
        """COMMANDER endpoints should require authentication."""
        response = app_client.post("/api/battlefield/init")
        assert response.status_code == 401


class TestViewerRoleAccess:
    """Verify VIEWER role access patterns."""

    def test_viewer_can_access_viewer_endpoints(self, app_client):
        """VIEWER should access VIEWER-level endpoints."""
        with patch('src.auth.middleware.get_current_user', return_value=make_auth_context(UserRole.VIEWER)):
            response = app_client.get("/api/runs/stats")
            assert response.status_code == 200

    def test_viewer_cannot_access_analyst_endpoints(self, app_client):
        """VIEWER should not access ANALYST-level endpoints."""
        with patch('src.auth.middleware.get_current_user', return_value=make_auth_context(UserRole.VIEWER)):
            response = app_client.get("/api/runs")
            assert response.status_code == 403

    def test_viewer_cannot_access_leadership_endpoints(self, app_client):
        """VIEWER should not access LEADERSHIP-level endpoints."""
        with patch('src.auth.middleware.get_current_user', return_value=make_auth_context(UserRole.VIEWER)):
            response = app_client.post("/api/battlefield/sync")
            assert response.status_code == 403

    def test_viewer_cannot_access_commander_endpoints(self, app_client):
        """VIEWER should not access COMMANDER-level endpoints."""
        with patch('src.auth.middleware.get_current_user', return_value=make_auth_context(UserRole.VIEWER)):
            response = app_client.post("/api/battlefield/init")
            assert response.status_code == 403


class TestAnalystRoleAccess:
    """Verify ANALYST role access patterns."""

    def test_analyst_can_access_viewer_endpoints(self, app_client):
        """ANALYST should access VIEWER-level endpoints (role hierarchy)."""
        with patch('src.auth.middleware.get_current_user', return_value=make_auth_context(UserRole.ANALYST)):
            response = app_client.get("/api/runs/stats")
            assert response.status_code == 200

    def test_analyst_can_access_analyst_endpoints(self, app_client):
        """ANALYST should access ANALYST-level endpoints."""
        with patch('src.auth.middleware.get_current_user', return_value=make_auth_context(UserRole.ANALYST)):
            response = app_client.get("/api/runs")
            assert response.status_code == 200

    def test_analyst_cannot_access_leadership_endpoints(self, app_client):
        """ANALYST should not access LEADERSHIP-level endpoints."""
        with patch('src.auth.middleware.get_current_user', return_value=make_auth_context(UserRole.ANALYST)):
            response = app_client.post("/api/battlefield/sync")
            assert response.status_code == 403

    def test_analyst_cannot_access_commander_endpoints(self, app_client):
        """ANALYST should not access COMMANDER-level endpoints."""
        with patch('src.auth.middleware.get_current_user', return_value=make_auth_context(UserRole.ANALYST)):
            response = app_client.post("/api/battlefield/init")
            assert response.status_code == 403


class TestLeadershipRoleAccess:
    """Verify LEADERSHIP role access patterns."""

    def test_leadership_can_access_viewer_endpoints(self, app_client):
        """LEADERSHIP should access VIEWER-level endpoints (role hierarchy)."""
        with patch('src.auth.middleware.get_current_user', return_value=make_auth_context(UserRole.LEADERSHIP)):
            response = app_client.get("/api/runs/stats")
            assert response.status_code == 200

    def test_leadership_can_access_analyst_endpoints(self, app_client):
        """LEADERSHIP should access ANALYST-level endpoints (role hierarchy)."""
        with patch('src.auth.middleware.get_current_user', return_value=make_auth_context(UserRole.LEADERSHIP)):
            response = app_client.get("/api/runs")
            assert response.status_code == 200

    def test_leadership_can_access_leadership_endpoints(self, app_client):
        """LEADERSHIP should access LEADERSHIP-level endpoints."""
        with patch('src.auth.middleware.get_current_user', return_value=make_auth_context(UserRole.LEADERSHIP)):
            response = app_client.post("/api/battlefield/sync")
            assert response.status_code == 200

    def test_leadership_cannot_access_commander_endpoints(self, app_client):
        """LEADERSHIP should not access COMMANDER-level endpoints."""
        with patch('src.auth.middleware.get_current_user', return_value=make_auth_context(UserRole.LEADERSHIP)):
            response = app_client.post("/api/battlefield/init")
            assert response.status_code == 403


class TestCommanderRoleAccess:
    """Verify COMMANDER role access patterns."""

    def test_commander_can_access_all_levels(self, app_client):
        """COMMANDER should access all endpoint levels."""
        with patch('src.auth.middleware.get_current_user', return_value=make_auth_context(UserRole.COMMANDER)):
            # VIEWER level
            response = app_client.get("/api/runs/stats")
            assert response.status_code == 200

            # ANALYST level
            response = app_client.get("/api/runs")
            assert response.status_code == 200

            # LEADERSHIP level
            response = app_client.post("/api/battlefield/sync")
            assert response.status_code == 200

            # COMMANDER level
            response = app_client.post("/api/battlefield/init")
            assert response.status_code == 200


class TestEvidenceEndpointRBAC:
    """Verify Evidence Pack endpoints require ANALYST role."""

    def test_evidence_packs_requires_analyst(self, app_client):
        """Evidence pack listing requires ANALYST."""
        # VIEWER should be rejected
        with patch('src.auth.middleware.get_current_user', return_value=make_auth_context(UserRole.VIEWER)):
            response = app_client.get("/api/evidence/packs")
            assert response.status_code == 403

        # ANALYST should be allowed
        with patch('src.auth.middleware.get_current_user', return_value=make_auth_context(UserRole.ANALYST)):
            response = app_client.get("/api/evidence/packs")
            assert response.status_code == 200

    def test_evidence_search_requires_analyst(self, app_client):
        """Evidence search requires ANALYST."""
        with patch('src.auth.middleware.get_current_user', return_value=make_auth_context(UserRole.VIEWER)):
            response = app_client.get("/api/evidence/search?q=test")
            assert response.status_code == 403

        with patch('src.auth.middleware.get_current_user', return_value=make_auth_context(UserRole.ANALYST)):
            response = app_client.get("/api/evidence/search?q=test")
            assert response.status_code == 200


class TestBattlefieldEndpointRBAC:
    """Verify Battlefield endpoints have correct RBAC."""

    def test_battlefield_stats_viewer_access(self, app_client):
        """Battlefield stats is VIEWER accessible (RBAC passes)."""
        with patch('src.auth.middleware.get_current_user', return_value=make_auth_context(UserRole.VIEWER)):
            try:
                response = app_client.get("/api/battlefield/stats")
                # Accept 200 or 500 (missing table) - verifies RBAC passed (not 401/403)
                assert response.status_code not in (401, 403), f"RBAC should allow VIEWER, got {response.status_code}"
            except Exception as e:
                # Database errors indicate RBAC passed but underlying query failed
                if "no such table" in str(e):
                    pass  # RBAC passed, just missing table
                else:
                    raise

    def test_battlefield_vehicle_update_requires_analyst(self, app_client):
        """Vehicle update requires ANALYST."""
        with patch('src.auth.middleware.get_current_user', return_value=make_auth_context(UserRole.VIEWER)):
            response = app_client.patch("/api/battlefield/vehicles/test-id", json={"our_posture": "support"})
            assert response.status_code == 403

    def test_battlefield_sync_requires_leadership(self, app_client):
        """Sync operation requires LEADERSHIP."""
        with patch('src.auth.middleware.get_current_user', return_value=make_auth_context(UserRole.ANALYST)):
            response = app_client.post("/api/battlefield/sync")
            assert response.status_code == 403

        with patch('src.auth.middleware.get_current_user', return_value=make_auth_context(UserRole.LEADERSHIP)):
            response = app_client.post("/api/battlefield/sync")
            assert response.status_code == 200


class TestRoleHierarchy:
    """Verify role hierarchy is properly enforced."""

    @pytest.mark.parametrize("role,expected_codes", [
        (UserRole.VIEWER, {"viewer": 200, "analyst": 403, "leadership": 403, "commander": 403}),
        (UserRole.ANALYST, {"viewer": 200, "analyst": 200, "leadership": 403, "commander": 403}),
        (UserRole.LEADERSHIP, {"viewer": 200, "analyst": 200, "leadership": 200, "commander": 403}),
        (UserRole.COMMANDER, {"viewer": 200, "analyst": 200, "leadership": 200, "commander": 200}),
    ])
    def test_role_hierarchy_enforcement(self, app_client, role, expected_codes):
        """Verify role hierarchy: higher roles include lower permissions."""
        endpoints = {
            "viewer": "/api/runs/stats",
            "analyst": "/api/runs",
            "leadership": "/api/battlefield/sync",
            "commander": "/api/battlefield/init",
        }

        with patch('src.auth.middleware.get_current_user', return_value=make_auth_context(role)):
            for level, endpoint in endpoints.items():
                if "sync" in endpoint or "init" in endpoint:
                    response = app_client.post(endpoint)
                else:
                    response = app_client.get(endpoint)

                expected = expected_codes[level]
                assert response.status_code == expected, \
                    f"{role.value} accessing {level} endpoint {endpoint}: expected {expected}, got {response.status_code}"
