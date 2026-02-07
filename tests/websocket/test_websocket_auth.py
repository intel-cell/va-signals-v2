"""WebSocket Authentication & CORS Security Tests.

Verifies:
- Unauthenticated WebSocket connections are rejected (4401)
- Invalid/expired tokens are rejected
- Valid tokens allow connection and extract user_id
- Incoming messages with bad tokens cause disconnect
- CORS headers are restricted (not wildcard)
"""

import time
from unittest.mock import patch

import pytest
from starlette.websockets import WebSocketDisconnect

# =============================================================================
# HELPERS
# =============================================================================


def _make_claims(user_id="ws-test-uid", email="ws@veteran-signals.com"):
    """Build mock Firebase token claims for WebSocket tests."""
    now = int(time.time())
    return {
        "user_id": user_id,
        "email": email,
        "display_name": "WS Test User",
        "iat": now,
        "exp": now + 3600,
    }


@pytest.fixture
def app_client():
    """TestClient for WebSocket + HTTP tests."""
    with patch("src.auth.firebase_config.init_firebase"):
        from fastapi.testclient import TestClient

        from src.dashboard_api import app

        yield TestClient(app)


# =============================================================================
# WEBSOCKET AUTH TESTS
# =============================================================================


class TestWebSocketAuthRequired:
    """WebSocket connections MUST provide a valid Firebase token."""

    def test_no_token_rejected(self, app_client):
        """Connection without token query param is rejected with 4401."""
        with (
            patch("src.websocket.api.verify_firebase_token", return_value=None),
            patch("src.websocket.api.init_firebase"),
        ):
            with pytest.raises(WebSocketDisconnect):
                with app_client.websocket_connect("/ws/signals"):
                    pass  # Should not reach here

    def test_empty_token_rejected(self, app_client):
        """Connection with empty token is rejected."""
        with (
            patch("src.websocket.api.verify_firebase_token", return_value=None),
            patch("src.websocket.api.init_firebase"),
        ):
            with pytest.raises(WebSocketDisconnect):
                with app_client.websocket_connect("/ws/signals?token="):
                    pass

    def test_invalid_token_rejected(self, app_client):
        """Connection with garbage token is rejected."""
        with (
            patch("src.websocket.api.verify_firebase_token", return_value=None),
            patch("src.websocket.api.init_firebase"),
        ):
            with pytest.raises(WebSocketDisconnect):
                with app_client.websocket_connect("/ws/signals?token=garbage-invalid-token"):
                    pass

    def test_expired_token_rejected(self, app_client):
        """Connection with expired token is rejected."""
        with (
            patch("src.websocket.api.verify_firebase_token", return_value=None),
            patch("src.websocket.api.init_firebase"),
        ):
            with pytest.raises(WebSocketDisconnect):
                with app_client.websocket_connect("/ws/signals?token=expired-token-value"):
                    pass


class TestWebSocketAuthValid:
    """Valid Firebase tokens allow WebSocket connection."""

    def test_valid_token_connects(self, app_client):
        """Valid Firebase token allows connection and receives welcome."""
        claims = _make_claims()
        with (
            patch("src.websocket.api.verify_firebase_token", return_value=claims),
            patch("src.websocket.api.init_firebase"),
        ):
            with app_client.websocket_connect("/ws/signals?token=valid-firebase-token") as ws:
                msg = ws.receive_json()
                assert msg["type"] == "connected"
                assert "client_id" in msg
                assert msg["message"] == "Connected to VA Signals real-time feed"

    def test_valid_token_extracts_user_id(self, app_client):
        """Valid token extracts user_id from Firebase claims."""
        claims = _make_claims(user_id="firebase-uid-123")
        with (
            patch("src.websocket.api.verify_firebase_token", return_value=claims),
            patch("src.websocket.api.init_firebase"),
        ):
            with app_client.websocket_connect("/ws/signals?token=valid-token") as ws:
                # Consume welcome
                ws.receive_json()
                # Request status to see user_id
                ws.send_json({"action": "status"})
                status = ws.receive_json()
                assert status["type"] == "status"
                assert status["user_id"] == "firebase-uid-123"

    def test_valid_token_with_client_id(self, app_client):
        """Valid token with explicit client_id preserves it."""
        claims = _make_claims()
        with (
            patch("src.websocket.api.verify_firebase_token", return_value=claims),
            patch("src.websocket.api.init_firebase"),
        ):
            with app_client.websocket_connect(
                "/ws/signals?token=valid-token&client_id=my-client-42"
            ) as ws:
                msg = ws.receive_json()
                assert msg["client_id"] == "my-client-42"

    def test_subscribe_works_after_auth(self, app_client):
        """Authenticated clients can subscribe to topics."""
        claims = _make_claims()
        with (
            patch("src.websocket.api.verify_firebase_token", return_value=claims),
            patch("src.websocket.api.init_firebase"),
        ):
            with app_client.websocket_connect("/ws/signals?token=valid-token") as ws:
                ws.receive_json()  # welcome
                ws.send_json({"action": "subscribe", "topics": ["alerts", "oversight"]})
                msg = ws.receive_json()
                assert msg["type"] == "subscribed"
                assert set(msg["topics"]) == {"alerts", "oversight"}


class TestWebSocketMessageRevalidation:
    """Incoming messages with token field are re-validated."""

    def test_message_with_invalid_token_disconnects(self, app_client):
        """Sending a message with an invalid token field closes connection."""
        claims = _make_claims()
        with (
            patch("src.websocket.api.verify_firebase_token") as mock_verify,
            patch("src.websocket.api.init_firebase"),
        ):
            # First call (connect) succeeds, second (message revalidation) fails
            mock_verify.side_effect = [claims, None]

            with app_client.websocket_connect("/ws/signals?token=valid-token") as ws:
                ws.receive_json()  # welcome
                # Send message with bad token — should trigger revalidation failure
                ws.send_json({"action": "status", "token": "now-expired-token"})
                error_msg = ws.receive_json()
                assert error_msg["type"] == "error"
                assert "Invalid or expired token" in error_msg["message"]

    def test_message_without_token_field_ok(self, app_client):
        """Messages without a token field do not trigger revalidation."""
        claims = _make_claims()
        with (
            patch("src.websocket.api.verify_firebase_token", return_value=claims),
            patch("src.websocket.api.init_firebase"),
        ):
            with app_client.websocket_connect("/ws/signals?token=valid-token") as ws:
                ws.receive_json()  # welcome
                ws.send_json({"action": "status"})
                msg = ws.receive_json()
                assert msg["type"] == "status"


# =============================================================================
# CORS HEADER TESTS
# =============================================================================


class TestCORSRestrictions:
    """CORS configuration must not use wildcard methods/headers."""

    def test_cors_allows_get(self, app_client):
        """CORS allows GET requests from configured origins."""
        response = app_client.options(
            "/health",
            headers={
                "Origin": "http://localhost:8000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200

    def test_cors_allows_post(self, app_client):
        """CORS allows POST requests from configured origins."""
        response = app_client.options(
            "/api/auth/login",
            headers={
                "Origin": "http://localhost:8000",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert response.status_code == 200

    def test_cors_rejects_patch(self, app_client):
        """CORS rejects PATCH method (not in allow list)."""
        response = app_client.options(
            "/health",
            headers={
                "Origin": "http://localhost:8000",
                "Access-Control-Request-Method": "PATCH",
            },
        )
        allow_methods = response.headers.get("access-control-allow-methods", "")
        assert "PATCH" not in allow_methods

    def test_cors_allows_authorization_header(self, app_client):
        """CORS allows Authorization header."""
        response = app_client.options(
            "/health",
            headers={
                "Origin": "http://localhost:8000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization",
            },
        )
        allow_headers = response.headers.get("access-control-allow-headers", "")
        assert "authorization" in allow_headers.lower()

    def test_cors_allows_content_type_header(self, app_client):
        """CORS allows Content-Type header."""
        response = app_client.options(
            "/health",
            headers={
                "Origin": "http://localhost:8000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )
        allow_headers = response.headers.get("access-control-allow-headers", "")
        assert "content-type" in allow_headers.lower()

    def test_cors_allows_csrf_header(self, app_client):
        """CORS allows X-CSRF-Token header."""
        response = app_client.options(
            "/health",
            headers={
                "Origin": "http://localhost:8000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "X-CSRF-Token",
            },
        )
        allow_headers = response.headers.get("access-control-allow-headers", "")
        assert "x-csrf-token" in allow_headers.lower()

    def test_cors_rejects_unauthorized_origin(self, app_client):
        """CORS rejects requests from non-whitelisted origins."""
        response = app_client.options(
            "/health",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        allow_origin = response.headers.get("access-control-allow-origin", "")
        assert allow_origin != "https://evil.example.com"
        assert allow_origin != "*"


# =============================================================================
# WEBSOCKET HEALTH ENDPOINT (unauthenticated — no change needed)
# =============================================================================


class TestWebSocketHealthEndpoint:
    """The /ws/health endpoint is a standard HTTP GET, not WebSocket."""

    def test_ws_health_accessible(self, app_client):
        """WebSocket health check returns status."""
        response = app_client.get("/ws/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "active_connections" in data
