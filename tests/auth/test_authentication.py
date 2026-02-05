"""Authentication Test Suite.

Tests authentication flows:
- Google OAuth login (primary production flow)
- Email/password login (secondary flow via Firebase)
- Session management (creation, persistence, logout)
- CSRF protection on state-changing operations

Uses mock Firebase token verification to avoid external dependencies.
"""

import time
import pytest
from unittest.mock import patch, MagicMock


# =============================================================================
# HELPERS
# =============================================================================

def _mock_claims(user_id="test-uid", email="test@veteran-signals.com",
                 display_name="Test User"):
    """Build mock Firebase token claims."""
    now = int(time.time())
    return {
        "user_id": user_id,
        "email": email,
        "display_name": display_name,
        "iat": now,
        "exp": now + 3600,
    }


def _mock_user_data(user_id="test-uid", email="test@veteran-signals.com",
                     display_name="Test User", role="viewer"):
    """Build mock user data as returned by _create_or_update_user."""
    return {
        "user_id": user_id,
        "email": email,
        "display_name": display_name,
        "role": role,
    }


@pytest.fixture(autouse=True)
def _reset_auth_rate_limiter():
    """Reset auth rate limiter between tests to prevent cross-test interference."""
    from src.auth.api import _auth_limiter
    _auth_limiter.reset()


@pytest.fixture
def app_client():
    """TestClient with mocked Firebase init."""
    with patch("src.auth.firebase_config.init_firebase"):
        from fastapi.testclient import TestClient
        from src.dashboard_api import app
        yield TestClient(app)


# =============================================================================
# GOOGLE LOGIN TESTS (Primary production flow: /api/auth/session)
# =============================================================================

class TestGoogleLogin:
    """Test Google OAuth authentication flow via /api/auth/session."""

    def test_google_login_success(self, app_client):
        """Test successful Google login: valid Firebase token creates session."""
        claims = _mock_claims()
        user_data = _mock_user_data()

        with patch("src.auth.api.verify_firebase_token", return_value=claims), \
             patch("src.auth.api._create_or_update_user", return_value=user_data):

            response = app_client.post("/api/auth/session", json={
                "idToken": "valid-firebase-token",
                "provider": "google",
                "rememberMe": False,
            })

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["user"]["email"] == "test@veteran-signals.com"
            assert data["user"]["role"] == "viewer"
            assert "csrf_token" in data

            # Verify session cookie was set
            assert "va_signals_session" in response.cookies

    def test_google_login_invalid_token(self, app_client):
        """Test Google login with invalid Firebase token returns 401."""
        with patch("src.auth.api.verify_firebase_token", return_value=None):
            response = app_client.post("/api/auth/session", json={
                "idToken": "invalid-token",
                "provider": "google",
            })

            assert response.status_code == 401
            assert "va_signals_session" not in response.cookies

    def test_google_login_expired_token(self, app_client):
        """Test Google login with expired token returns 401."""
        # verify_firebase_token returns None for expired tokens
        with patch("src.auth.api.verify_firebase_token", return_value=None):
            response = app_client.post("/api/auth/session", json={
                "idToken": "expired-token",
                "provider": "google",
            })

            assert response.status_code == 401


# =============================================================================
# EMAIL LOGIN TESTS (Secondary flow: /api/auth/login)
# =============================================================================

class TestEmailLogin:
    """Test email/password authentication via /api/auth/login.

    Note: The 'password' field is actually a Firebase ID token obtained
    after the client authenticates with Firebase email/password.
    """

    def test_email_login_success(self, app_client):
        """Test successful email login with valid Firebase ID token."""
        claims = _mock_claims(email="user@veteran-signals.com")
        user_data = _mock_user_data(email="user@veteran-signals.com")

        with patch("src.auth.api.verify_firebase_token", return_value=claims), \
             patch("src.auth.api._create_or_update_user", return_value=user_data):

            response = app_client.post("/api/auth/login", json={
                "email": "user@veteran-signals.com",
                "password": "firebase-id-token",
            })

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["user"]["email"] == "user@veteran-signals.com"
            assert "va_signals_session" in response.cookies

    def test_email_login_wrong_password(self, app_client):
        """Test login with invalid Firebase token returns 401."""
        with patch("src.auth.api.verify_firebase_token", return_value=None):
            response = app_client.post("/api/auth/login", json={
                "email": "user@veteran-signals.com",
                "password": "bad-token",
            })

            assert response.status_code == 401
            assert "va_signals_session" not in response.cookies

    def test_email_login_nonexistent_user(self, app_client):
        """Test login with invalid token for non-existent user returns 401."""
        with patch("src.auth.api.verify_firebase_token", return_value=None):
            response = app_client.post("/api/auth/login", json={
                "email": "nobody@veteran-signals.com",
                "password": "any-token",
            })

            # Returns 401 (same as wrong password — no user enumeration)
            assert response.status_code == 401

    def test_email_login_email_mismatch(self, app_client):
        """Test login fails when token email doesn't match request email."""
        # Token is valid but for a different email
        claims = _mock_claims(email="real@veteran-signals.com")

        with patch("src.auth.api.verify_firebase_token", return_value=claims):
            response = app_client.post("/api/auth/login", json={
                "email": "different@veteran-signals.com",
                "password": "valid-token-wrong-email",
            })

            assert response.status_code == 401


# =============================================================================
# SESSION MANAGEMENT TESTS
# =============================================================================

class TestSessionManagement:
    """Test session handling: creation, persistence, and logout."""

    def test_session_persistence(self, app_client):
        """Test session created via /api/auth/session persists for /api/auth/me."""
        claims = _mock_claims()
        user_data = _mock_user_data()

        with patch("src.auth.api.verify_firebase_token", return_value=claims), \
             patch("src.auth.api._create_or_update_user", return_value=user_data):

            # Step 1: Create session
            session_resp = app_client.post("/api/auth/session", json={
                "idToken": "valid-token",
                "provider": "google",
            })
            assert session_resp.status_code == 200

        # Step 2: Use the session cookie to access /api/auth/me
        # The TestClient automatically carries cookies forward.
        # We mock _get_user_role since there's no real DB in tests.
        from src.auth.models import UserRole
        with patch("src.auth.middleware.AuthMiddleware._get_user_role",
                   return_value=UserRole.VIEWER):
            me_resp = app_client.get("/api/auth/me")
            # Session cookie authenticates the request — should get 200
            assert me_resp.status_code == 200
            data = me_resp.json()
            assert data["email"] == "test@veteran-signals.com"

    def test_session_timeout(self, app_client):
        """Test expired session token is rejected."""
        from src.auth.firebase_config import create_session_token, verify_session_token

        # Create a token that expires immediately
        token = create_session_token("test-uid", "test@test.com", expires_in_hours=0)

        # Advance time conceptually — the token with 0 hours expiry should
        # be expired at verification time (or very close to it)
        result = verify_session_token(token)
        # With 0 hours, the token expires at creation time
        # verify_session_token checks exp < now, so it should be None or valid
        # depending on timing. The important thing is the mechanism works.
        # For a definitive test, we mock time:
        with patch("src.auth.firebase_config.datetime") as mock_dt:
            from datetime import datetime, timezone, timedelta
            # Set "now" to 2 hours in the future
            future = datetime.now(timezone.utc) + timedelta(hours=2)
            mock_dt.now.return_value = future
            mock_dt.fromtimestamp = datetime.fromtimestamp
            result = verify_session_token(token)
            assert result is None, "Expired session token should be rejected"

    def test_logout_clears_session(self, app_client):
        """Test logout clears session cookies."""
        claims = _mock_claims()
        user_data = _mock_user_data()

        # Step 1: Create session
        with patch("src.auth.api.verify_firebase_token", return_value=claims), \
             patch("src.auth.api._create_or_update_user", return_value=user_data):
            session_resp = app_client.post("/api/auth/session", json={
                "idToken": "valid-token",
                "provider": "google",
            })
            assert session_resp.status_code == 200
            assert "va_signals_session" in session_resp.cookies

        # Step 2: Logout
        logout_resp = app_client.post("/api/auth/logout")
        # Logout should work even without full auth (clears cookies)
        assert logout_resp.status_code == 200
        assert logout_resp.json()["status"] == "logged_out"

        # Verify cookies are cleared (set to empty/deleted)
        # After logout, the session cookie should be deleted
        set_cookie_headers = logout_resp.headers.get_list("set-cookie")
        session_cleared = any(
            "va_signals_session" in h and ('=""' in h or "max-age=0" in h or 'expires=' in h.lower())
            for h in set_cookie_headers
        )
        assert session_cleared, f"Session cookie not cleared. Headers: {set_cookie_headers}"

    def test_session_cookie_secure_flags(self, app_client):
        """Test session cookie has proper security flags."""
        claims = _mock_claims()
        user_data = _mock_user_data()

        with patch("src.auth.api.verify_firebase_token", return_value=claims), \
             patch("src.auth.api._create_or_update_user", return_value=user_data):

            response = app_client.post("/api/auth/session", json={
                "idToken": "valid-token",
                "provider": "google",
            })

            # Check Set-Cookie headers for security flags
            set_cookie_headers = response.headers.get_list("set-cookie")
            session_cookie = [h for h in set_cookie_headers if "va_signals_session" in h]
            assert len(session_cookie) == 1, "Should set exactly one session cookie"

            cookie_str = session_cookie[0].lower()
            assert "httponly" in cookie_str, "Session cookie must be httpOnly"
            assert "samesite=lax" in cookie_str, "Session cookie should have SameSite=Lax"


# =============================================================================
# PASSWORD RESET TESTS
# =============================================================================

class TestPasswordReset:
    """Test password reset flow.

    Note: Password reset is handled entirely client-side by Firebase SDK.
    The backend has no password reset endpoint. These tests verify the
    expected behavior when no such endpoint exists.
    """

    def test_password_reset_handled_by_firebase(self):
        """Password reset is a client-side Firebase operation — no backend endpoint."""
        # Firebase SDK handles sendPasswordResetEmail() entirely client-side.
        # The backend doesn't expose a /api/auth/reset-password endpoint.
        # This test documents that design decision.
        from src.auth import api
        route_paths = [r.path for r in api.router.routes if hasattr(r, "path")]
        assert "/reset-password" not in route_paths
        assert "/forgot-password" not in route_paths

    def test_password_reset_no_user_enumeration(self, app_client):
        """Verify no endpoint leaks whether an email exists."""
        # POST to a non-existent reset endpoint should NOT return 200 or 400
        # (which would indicate the endpoint exists and processes requests).
        # It may return 403 (CSRF), 404, or 405 — all acceptable since
        # they don't leak user existence info.
        response = app_client.post("/api/auth/reset-password", json={
            "email": "test@veteran-signals.com"
        })
        assert response.status_code not in (200, 400), \
            "Should not have a functioning reset-password endpoint"


# =============================================================================
# CSRF PROTECTION TESTS
# =============================================================================

class TestCSRFProtection:
    """Test CSRF protection on state-changing operations."""

    def _get_csrf_token(self, client):
        """Helper to get a CSRF token and cookie from the server."""
        resp = client.get("/api/auth/csrf")
        assert resp.status_code == 200
        return resp.json()["csrf_token"]

    def test_csrf_protection_on_post(self, app_client):
        """POST with session auth but no CSRF token gets 403."""
        from src.auth.models import AuthContext, UserRole

        mock_auth = AuthContext(
            user_id="test-uid",
            email="test@veteran-signals.com",
            role=UserRole.COMMANDER,
            display_name="Test",
            auth_method="session",  # Session auth requires CSRF
        )

        # Must mock at middleware._authenticate so the CSRF check in dispatch()
        # sees this as a session-authenticated request.
        with patch("src.auth.middleware.AuthMiddleware._authenticate",
                   return_value=mock_auth):
            # POST to a non-CSRF-exempt endpoint without CSRF token
            response = app_client.post("/api/auth/users", json={
                "email": "new@veteran-signals.com",
                "role": "viewer",
            })
            assert response.status_code == 403, \
                "Session-authed POST without CSRF should be rejected"

    def test_csrf_token_provided(self, app_client):
        """POST with matching CSRF cookie and header succeeds."""
        from src.auth.models import AuthContext, UserRole

        mock_auth = AuthContext(
            user_id="test-uid",
            email="test@veteran-signals.com",
            role=UserRole.COMMANDER,
            display_name="Test",
            auth_method="session",
        )

        # Get a CSRF token (sets the cookie)
        csrf_token = self._get_csrf_token(app_client)

        with patch("src.auth.middleware.AuthMiddleware._authenticate",
                   return_value=mock_auth), \
             patch("src.auth.api._get_user_by_email", return_value=None), \
             patch("src.auth.api._execute_write"):

            response = app_client.post(
                "/api/auth/users",
                json={"email": "new@veteran-signals.com", "role": "viewer"},
                headers={"X-CSRF-Token": csrf_token},
                cookies={"csrf_token": csrf_token},
            )
            # Should not be 403 (CSRF passed)
            assert response.status_code != 403, \
                f"CSRF should pass with valid token. Got {response.status_code}"

    def test_csrf_token_invalid(self, app_client):
        """POST with mismatched CSRF cookie and header gets 403."""
        from src.auth.models import AuthContext, UserRole

        mock_auth = AuthContext(
            user_id="test-uid",
            email="test@veteran-signals.com",
            role=UserRole.COMMANDER,
            display_name="Test",
            auth_method="session",
        )

        with patch("src.auth.middleware.AuthMiddleware._authenticate",
                   return_value=mock_auth):
            response = app_client.post(
                "/api/auth/users",
                json={"email": "new@veteran-signals.com", "role": "viewer"},
                headers={"X-CSRF-Token": "wrong-token"},
                cookies={"csrf_token": "different-token"},
            )
            assert response.status_code == 403, \
                "Mismatched CSRF tokens should be rejected"

    def test_csrf_not_required_for_bearer_auth(self, app_client):
        """Bearer token auth should bypass CSRF (API clients).

        The CSRF check in AuthMiddleware is lenient for non-session auth:
        if auth_context.auth_method != 'session', CSRF is not enforced.
        We must mock at the middleware._authenticate level so the middleware
        itself sees the Firebase auth context during dispatch.
        """
        from src.auth.models import AuthContext, UserRole

        mock_auth = AuthContext(
            user_id="test-uid",
            email="test@veteran-signals.com",
            role=UserRole.COMMANDER,
            display_name="Test",
            auth_method="firebase",  # Bearer auth, not session
        )

        # Mock _authenticate at the middleware level so CSRF check sees firebase auth
        with patch("src.auth.middleware.AuthMiddleware._authenticate",
                   return_value=mock_auth), \
             patch("src.auth.api._get_user_by_email", return_value=None), \
             patch("src.auth.api._execute_write"):

            response = app_client.post(
                "/api/auth/users",
                json={"email": "new@veteran-signals.com", "role": "viewer"},
                headers={"Authorization": "Bearer mock-token"},
                # No CSRF header — should still work for Bearer auth
            )
            assert response.status_code != 403, \
                f"Bearer auth should not require CSRF. Got {response.status_code}"


# =============================================================================
# RATE LIMITING TESTS
# =============================================================================

class TestAuthRateLimiting:
    """Test per-IP rate limiting on auth endpoints."""

    def test_rate_limit_triggers_after_burst(self, app_client):
        """Auth endpoints return 429 after burst limit exceeded."""
        with patch("src.auth.api.verify_firebase_token", return_value=None):
            # Send requests up to the burst limit (5 by default)
            for i in range(5):
                response = app_client.post("/api/auth/login", json={
                    "email": "attacker@example.com",
                    "password": "bad-token",
                })
                # Should be 401 (invalid token), NOT 429
                assert response.status_code == 401, \
                    f"Request {i+1} should be allowed, got {response.status_code}"

            # Next request should be rate limited
            response = app_client.post("/api/auth/login", json={
                "email": "attacker@example.com",
                "password": "bad-token",
            })
            assert response.status_code == 429, \
                "Should be rate limited after burst exceeded"
            assert "Retry-After" in response.headers

    def test_rate_limit_applies_to_session_endpoint(self, app_client):
        """Rate limit also applies to /api/auth/session."""
        with patch("src.auth.api.verify_firebase_token", return_value=None):
            for _ in range(5):
                app_client.post("/api/auth/session", json={
                    "idToken": "bad-token",
                    "provider": "google",
                })

            response = app_client.post("/api/auth/session", json={
                "idToken": "bad-token",
                "provider": "google",
            })
            assert response.status_code == 429

    def test_rate_limit_per_ip_isolation(self, app_client):
        """Different IPs have independent rate limits."""
        from src.auth.api import _auth_limiter

        # Exhaust limit for one IP
        for _ in range(5):
            _auth_limiter.check("192.168.1.1")

        # First IP should be limited
        allowed, _ = _auth_limiter.check("192.168.1.1")
        assert not allowed, "First IP should be rate limited"

        # Second IP should still have full quota
        allowed, _ = _auth_limiter.check("192.168.1.2")
        assert allowed, "Second IP should not be affected"
