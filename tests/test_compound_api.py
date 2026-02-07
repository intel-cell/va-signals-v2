"""Tests for compound signals API endpoints.

Covers:
- GET /api/compound/signals — list with filters
- GET /api/compound/signals/{compound_id} — single detail
- POST /api/compound/signals/{compound_id}/resolve — mark resolved
- GET /api/compound/stats — aggregate stats
- POST /api/compound/run — trigger engine manually
- Auth enforcement (401/403)
- 404 handling
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.auth.models import AuthContext, UserRole

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_auth_context(role: UserRole) -> AuthContext:
    return AuthContext(
        user_id=f"test-{role.value}-uid",
        email=f"{role.value}@veteran-signals.com",
        role=role,
        display_name=f"Test {role.value.title()}",
        auth_method="firebase",
    )


@pytest.fixture
def client():
    with patch("src.auth.firebase_config.init_firebase"):
        from src.dashboard_api import app

        return TestClient(app)


def _auth(role: UserRole):
    """Context manager to mock auth with given role."""
    return patch(
        "src.auth.middleware.get_current_user",
        return_value=make_auth_context(role),
    )


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_SIGNAL = {
    "compound_id": "cs-abc123",
    "rule_id": "oversight_legislative",
    "severity_score": 0.75,
    "narrative": "Correlated 3 events across oversight, bill.",
    "temporal_window_hours": 72,
    "member_events": [
        {
            "source_type": "oversight",
            "event_id": "ev-1",
            "title": "GAO Report",
            "timestamp": "2026-02-01T00:00:00Z",
        },
        {
            "source_type": "bill",
            "event_id": "ev-2",
            "title": "HR 1234",
            "timestamp": "2026-02-02T00:00:00Z",
        },
    ],
    "topics": ["disability_benefits", "claims_backlog"],
    "created_at": "2026-02-05T12:00:00Z",
    "resolved_at": None,
}

SAMPLE_SIGNAL_2 = {
    **SAMPLE_SIGNAL,
    "compound_id": "cs-def456",
    "rule_id": "regulatory_hearing",
    "severity_score": 0.55,
}

SAMPLE_STATS = {
    "total": 10,
    "unresolved": 7,
    "resolved": 3,
    "by_rule": {"oversight_legislative": 6, "regulatory_hearing": 4},
}


# ===========================================================================
# GET /api/compound/signals
# ===========================================================================


class TestListCompoundSignals:
    """GET /api/compound/signals"""

    @patch(
        "src.routers.compound.get_compound_signals", return_value=[SAMPLE_SIGNAL, SAMPLE_SIGNAL_2]
    )
    def test_list_signals_ok(self, mock_get, client):
        with _auth(UserRole.VIEWER):
            resp = client.get("/api/compound/signals")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["signals"]) == 2
        assert data["limit"] == 20
        assert data["offset"] == 0

    @patch("src.routers.compound.get_compound_signals", return_value=[SAMPLE_SIGNAL])
    def test_list_signals_with_filters(self, mock_get, client):
        with _auth(UserRole.VIEWER):
            resp = client.get(
                "/api/compound/signals",
                params={
                    "limit": 5,
                    "offset": 10,
                    "rule_id": "oversight_legislative",
                    "min_severity": 0.5,
                },
            )
        assert resp.status_code == 200
        mock_get.assert_called_once_with(
            limit=5,
            offset=10,
            rule_id="oversight_legislative",
            min_severity=0.5,
        )
        data = resp.json()
        assert data["limit"] == 5
        assert data["offset"] == 10

    @patch("src.routers.compound.get_compound_signals", return_value=[])
    def test_list_signals_empty(self, mock_get, client):
        with _auth(UserRole.VIEWER):
            resp = client.get("/api/compound/signals")
        assert resp.status_code == 200
        data = resp.json()
        assert data["signals"] == []
        assert data["total"] == 0

    def test_list_signals_unauthenticated(self, client):
        resp = client.get("/api/compound/signals")
        assert resp.status_code == 401

    @patch("src.routers.compound.get_compound_signals", return_value=[SAMPLE_SIGNAL])
    def test_list_signals_default_params(self, mock_get, client):
        with _auth(UserRole.ANALYST):
            resp = client.get("/api/compound/signals")
        assert resp.status_code == 200
        mock_get.assert_called_once_with(limit=20, offset=0, rule_id=None, min_severity=None)


# ===========================================================================
# GET /api/compound/signals/{compound_id}
# ===========================================================================


class TestGetCompoundSignal:
    """GET /api/compound/signals/{compound_id}"""

    @patch("src.routers.compound.get_compound_signal", return_value=SAMPLE_SIGNAL)
    def test_get_signal_ok(self, mock_get, client):
        with _auth(UserRole.VIEWER):
            resp = client.get("/api/compound/signals/cs-abc123")
        assert resp.status_code == 200
        data = resp.json()
        assert data["compound_id"] == "cs-abc123"
        assert data["rule_id"] == "oversight_legislative"
        assert len(data["member_events"]) == 2
        assert data["topics"] == ["disability_benefits", "claims_backlog"]

    @patch("src.routers.compound.get_compound_signal", return_value=None)
    def test_get_signal_not_found(self, mock_get, client):
        with _auth(UserRole.VIEWER):
            resp = client.get("/api/compound/signals/cs-nonexistent")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_get_signal_unauthenticated(self, client):
        resp = client.get("/api/compound/signals/cs-abc123")
        assert resp.status_code == 401

    @patch("src.routers.compound.get_compound_signal", return_value=SAMPLE_SIGNAL)
    def test_get_signal_response_fields(self, mock_get, client):
        with _auth(UserRole.VIEWER):
            resp = client.get("/api/compound/signals/cs-abc123")
        data = resp.json()
        assert "severity_score" in data
        assert "narrative" in data
        assert "temporal_window_hours" in data
        assert "created_at" in data
        assert "resolved_at" in data


# ===========================================================================
# POST /api/compound/signals/{compound_id}/resolve
# ===========================================================================


class TestResolveCompoundSignal:
    """POST /api/compound/signals/{compound_id}/resolve"""

    @patch("src.routers.compound.resolve_compound_signal", return_value=True)
    def test_resolve_ok(self, mock_resolve, client):
        with _auth(UserRole.ANALYST):
            resp = client.post("/api/compound/signals/cs-abc123/resolve")
        assert resp.status_code == 200
        data = resp.json()
        assert data["resolved"] is True
        assert data["compound_id"] == "cs-abc123"

    @patch("src.routers.compound.resolve_compound_signal", return_value=False)
    def test_resolve_not_found_or_already_resolved(self, mock_resolve, client):
        with _auth(UserRole.ANALYST):
            resp = client.post("/api/compound/signals/cs-nonexistent/resolve")
        assert resp.status_code == 404

    def test_resolve_unauthenticated(self, client):
        resp = client.post("/api/compound/signals/cs-abc123/resolve")
        assert resp.status_code == 401

    @patch("src.routers.compound.resolve_compound_signal", return_value=True)
    def test_resolve_viewer_forbidden(self, mock_resolve, client):
        with _auth(UserRole.VIEWER):
            resp = client.post("/api/compound/signals/cs-abc123/resolve")
        assert resp.status_code == 403

    @patch("src.routers.compound.resolve_compound_signal", return_value=True)
    def test_resolve_commander_allowed(self, mock_resolve, client):
        with _auth(UserRole.COMMANDER):
            resp = client.post("/api/compound/signals/cs-abc123/resolve")
        assert resp.status_code == 200


# ===========================================================================
# GET /api/compound/stats
# ===========================================================================


class TestCompoundStats:
    """GET /api/compound/stats"""

    @patch("src.routers.compound.get_compound_stats", return_value=SAMPLE_STATS)
    def test_stats_ok(self, mock_stats, client):
        with _auth(UserRole.VIEWER):
            resp = client.get("/api/compound/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_signals"] == 10
        assert data["unresolved"] == 7
        assert data["by_rule"]["oversight_legislative"] == 6
        assert "checked_at" in data

    def test_stats_unauthenticated(self, client):
        resp = client.get("/api/compound/stats")
        assert resp.status_code == 401

    @patch(
        "src.routers.compound.get_compound_stats",
        return_value={"total": 0, "unresolved": 0, "resolved": 0, "by_rule": {}},
    )
    def test_stats_empty(self, mock_stats, client):
        with _auth(UserRole.VIEWER):
            resp = client.get("/api/compound/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_signals"] == 0
        assert data["avg_severity"] == 0.0

    @patch("src.routers.compound.get_compound_stats", return_value=SAMPLE_STATS)
    def test_stats_response_fields(self, mock_stats, client):
        with _auth(UserRole.VIEWER):
            resp = client.get("/api/compound/stats")
        data = resp.json()
        required_fields = ["total_signals", "unresolved", "by_rule", "avg_severity", "checked_at"]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"


# ===========================================================================
# POST /api/compound/run
# ===========================================================================


class TestRunCorrelationEngine:
    """POST /api/compound/run"""

    @patch("src.routers.compound.CorrelationEngine")
    def test_run_ok(self, MockEngine, client):
        mock_instance = MagicMock()
        mock_instance.run.return_value = {
            "total_signals": 5,
            "stored": 3,
            "by_rule": {"oversight_legislative": 5},
        }
        MockEngine.return_value = mock_instance
        with _auth(UserRole.ANALYST):
            resp = client.post("/api/compound/run")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_signals"] == 5
        assert data["stored"] == 3
        MockEngine.assert_called_once()
        mock_instance.run.assert_called_once()

    def test_run_unauthenticated(self, client):
        resp = client.post("/api/compound/run")
        assert resp.status_code == 401

    @patch("src.routers.compound.CorrelationEngine")
    def test_run_viewer_forbidden(self, MockEngine, client):
        with _auth(UserRole.VIEWER):
            resp = client.post("/api/compound/run")
        assert resp.status_code == 403

    @patch("src.routers.compound.CorrelationEngine")
    def test_run_commander_allowed(self, MockEngine, client):
        mock_instance = MagicMock()
        mock_instance.run.return_value = {"total_signals": 0, "stored": 0, "by_rule": {}}
        MockEngine.return_value = mock_instance
        with _auth(UserRole.COMMANDER):
            resp = client.post("/api/compound/run")
        assert resp.status_code == 200

    @patch("src.routers.compound.CorrelationEngine")
    def test_run_engine_error(self, MockEngine, client):
        mock_instance = MagicMock()
        mock_instance.run.side_effect = Exception("DB error")
        MockEngine.return_value = mock_instance
        with _auth(UserRole.ANALYST):
            resp = client.post("/api/compound/run")
        assert resp.status_code == 500
        assert "error" in resp.json()["detail"].lower()


# ===========================================================================
# Role hierarchy tests
# ===========================================================================


class TestRoleHierarchy:
    """Verify role hierarchy across compound endpoints."""

    @patch("src.routers.compound.get_compound_signals", return_value=[])
    def test_commander_can_read(self, mock_get, client):
        with _auth(UserRole.COMMANDER):
            resp = client.get("/api/compound/signals")
        assert resp.status_code == 200

    @patch("src.routers.compound.get_compound_signals", return_value=[])
    def test_analyst_can_read(self, mock_get, client):
        with _auth(UserRole.ANALYST):
            resp = client.get("/api/compound/signals")
        assert resp.status_code == 200

    @patch("src.routers.compound.get_compound_signals", return_value=[])
    def test_leadership_can_read(self, mock_get, client):
        with _auth(UserRole.LEADERSHIP):
            resp = client.get("/api/compound/signals")
        assert resp.status_code == 200

    @patch("src.routers.compound.resolve_compound_signal", return_value=True)
    def test_leadership_can_resolve(self, mock_resolve, client):
        with _auth(UserRole.LEADERSHIP):
            resp = client.post("/api/compound/signals/cs-abc123/resolve")
        assert resp.status_code == 200
