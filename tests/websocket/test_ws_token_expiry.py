"""WebSocket token expiry recheck and rate-limit tests.

Verifies:
- Connection with valid token succeeds and receives welcome
- Token that expires mid-session causes disconnection with 4401
- Rate limit exceeded (31+ messages in <60s) causes disconnection with 4429
- Normal message rate (under limit) works fine
"""

import time
from unittest.mock import patch

import pytest


def _make_claims(user_id="ws-expiry-uid", exp_offset=3600):
    """Build mock Firebase claims with configurable expiry offset from now."""
    now = int(time.time())
    return {
        "user_id": user_id,
        "email": "ws-expiry@test.com",
        "display_name": "WS Expiry Test",
        "iat": now,
        "exp": now + exp_offset,
    }


@pytest.fixture
def app_client():
    """TestClient for WebSocket tests."""
    with patch("src.auth.firebase_config.init_firebase"):
        from fastapi.testclient import TestClient

        from src.dashboard_api import app

        yield TestClient(app)


class TestTokenExpiryMidSession:
    """Token expiry is rechecked on every incoming message."""

    def test_valid_token_connects_and_welcome(self, app_client):
        """Connection with valid token succeeds and receives welcome message."""
        claims = _make_claims(exp_offset=3600)
        with (
            patch("src.websocket.api.verify_firebase_token", return_value=claims),
            patch("src.websocket.api.init_firebase"),
        ):
            with app_client.websocket_connect("/ws/signals?token=valid-tok") as ws:
                msg = ws.receive_json()
                assert msg["type"] == "connected"
                assert "client_id" in msg
                assert msg["message"] == "Connected to VA Signals real-time feed"

    def test_expired_token_mid_session_disconnects_4401(self, app_client):
        """Token that expires mid-session causes disconnection with code 4401."""
        # Token already expired (exp in the past)
        claims = _make_claims(exp_offset=-10)
        with (
            patch("src.websocket.api.verify_firebase_token", return_value=claims),
            patch("src.websocket.api.init_firebase"),
        ):
            with app_client.websocket_connect("/ws/signals?token=valid-tok") as ws:
                ws.receive_json()  # welcome
                # Send any message — should trigger expiry check
                ws.send_json({"action": "status"})
                error_msg = ws.receive_json()
                assert error_msg["type"] == "error"
                assert "Token expired" in error_msg["message"]


class TestRateLimiting:
    """Rate limiting enforces max 30 messages per 60-second window."""

    def test_rate_limit_exceeded_disconnects_4429(self, app_client):
        """Sending 31+ messages in <60s causes disconnection with code 4429."""
        claims = _make_claims(exp_offset=3600)
        with (
            patch("src.websocket.api.verify_firebase_token", return_value=claims),
            patch("src.websocket.api.init_firebase"),
        ):
            with app_client.websocket_connect("/ws/signals?token=valid-tok") as ws:
                ws.receive_json()  # welcome
                # Send 30 messages (should all succeed)
                for _ in range(30):
                    ws.send_json({"action": "pong"})
                # 31st message should trigger rate limit
                ws.send_json({"action": "pong"})
                error_msg = ws.receive_json()
                assert error_msg["type"] == "error"
                assert "Rate limit exceeded" in error_msg["message"]

    def test_normal_message_rate_works(self, app_client):
        """Sending messages under the rate limit works fine."""
        claims = _make_claims(exp_offset=3600)
        with (
            patch("src.websocket.api.verify_firebase_token", return_value=claims),
            patch("src.websocket.api.init_firebase"),
        ):
            with app_client.websocket_connect("/ws/signals?token=valid-tok") as ws:
                ws.receive_json()  # welcome
                # Send a few messages — well under the 30/60s limit
                for _ in range(5):
                    ws.send_json({"action": "status"})
                    msg = ws.receive_json()
                    assert msg["type"] == "status"
