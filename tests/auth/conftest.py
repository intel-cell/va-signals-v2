"""Fixtures for authentication tests.

HOTEL COMMAND - Test fixtures for auth testing.

ECHO auth module integrated - fixtures now operational.
Updated: 2026-02-04
"""

import time
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

# =============================================================================
# TEST USER FIXTURES
# =============================================================================


@pytest.fixture
def commander_user() -> dict:
    """Commander role test user."""
    return {
        "email": "commander@veteran-signals.com",
        "role": "commander",
        "user_id": "test-commander-uid",
        "display_name": "Test Commander",
    }


@pytest.fixture
def leadership_user() -> dict:
    """Leadership role test user."""
    return {
        "email": "leadership@veteran-signals.com",
        "role": "leadership",
        "user_id": "test-leadership-uid",
        "display_name": "Test Leadership",
    }


@pytest.fixture
def analyst_user() -> dict:
    """Analyst role test user."""
    return {
        "email": "analyst@veteran-signals.com",
        "role": "analyst",
        "user_id": "test-analyst-uid",
        "display_name": "Test Analyst",
    }


@pytest.fixture
def viewer_user() -> dict:
    """Viewer role test user."""
    return {
        "email": "viewer@veteran-signals.com",
        "role": "viewer",
        "user_id": "test-viewer-uid",
        "display_name": "Test Viewer",
    }


@pytest.fixture
def unauthenticated_user() -> dict:
    """No user - unauthenticated request."""
    return {}


# =============================================================================
# MOCK TOKEN FIXTURES
# =============================================================================


def _make_mock_token_claims(user: dict) -> dict:
    """Create mock Firebase token claims from user dict."""
    now = int(time.time())
    return {
        "user_id": user.get("user_id", "test-uid"),
        "email": user.get("email", "test@example.com"),
        "display_name": user.get("display_name", "Test User"),
        "iat": now,
        "exp": now + 3600,  # 1 hour
    }


@pytest.fixture
def valid_firebase_token() -> str:
    """Mock valid Firebase ID token."""
    return "mock-valid-firebase-token"


@pytest.fixture
def expired_firebase_token() -> str:
    """Mock expired Firebase ID token."""
    return "mock-expired-firebase-token"


@pytest.fixture
def invalid_firebase_token() -> str:
    """Mock invalid Firebase ID token."""
    return "mock-invalid-firebase-token"


# =============================================================================
# APP CLIENT FIXTURES
# =============================================================================


@pytest.fixture
def test_client():
    """
    FastAPI TestClient with auth middleware.

    Uses real app with mocked Firebase verification.
    """
    from fastapi.testclient import TestClient

    from src.dashboard_api import app

    return TestClient(app)


@pytest.fixture
def mock_firebase_verify():
    """Fixture to mock Firebase token verification."""
    with patch("src.auth.firebase_config.verify_firebase_token") as mock:
        yield mock


@pytest.fixture
def authenticated_client_as(test_client, mock_firebase_verify):
    """
    Factory fixture to create authenticated client for any user.

    Usage:
        def test_something(authenticated_client_as, commander_user):
            client = authenticated_client_as(commander_user)
            response = client.get("/api/runs")
            assert response.status_code == 200
    """

    def _create_client(user: dict):
        # Mock Firebase to return this user's claims
        mock_firebase_verify.return_value = _make_mock_token_claims(user)
        test_client.headers["Authorization"] = "Bearer mock-token"
        return test_client

    return _create_client


@pytest.fixture
def authenticated_client(test_client, mock_firebase_verify, viewer_user):
    """
    TestClient authenticated as viewer (lowest privilege).

    For specific role testing, use authenticated_client_as fixture.
    """
    mock_firebase_verify.return_value = _make_mock_token_claims(viewer_user)
    test_client.headers["Authorization"] = "Bearer mock-viewer-token"
    return test_client


# =============================================================================
# DATABASE FIXTURES
# =============================================================================


@pytest.fixture
def test_db():
    """
    Test database with auth tables.

    Creates an in-memory SQLite database with users table.
    """
    import sqlite3

    con = sqlite3.connect(":memory:")
    con.execute("""
        CREATE TABLE users (
            user_id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            display_name TEXT,
            role TEXT NOT NULL DEFAULT 'viewer',
            created_at TEXT DEFAULT (datetime('now')),
            last_login TEXT,
            is_active INTEGER DEFAULT 1,
            created_by TEXT,
            CONSTRAINT valid_role CHECK (role IN ('commander', 'leadership', 'analyst', 'viewer'))
        )
    """)
    con.execute("""
        CREATE TABLE audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            user_email TEXT,
            action TEXT NOT NULL,
            resource TEXT,
            result TEXT,
            details TEXT
        )
    """)
    con.commit()
    yield con
    con.close()


@pytest.fixture
def seeded_test_db(test_db):
    """Test database with seeded test users."""

    now = datetime.now(UTC).isoformat()
    users = [
        ("test-commander-uid", "commander@veteran-signals.com", "Test Commander", "commander", now),
        (
            "test-leadership-uid",
            "leadership@veteran-signals.com",
            "Test Leadership",
            "leadership",
            now,
        ),
        ("test-analyst-uid", "analyst@veteran-signals.com", "Test Analyst", "analyst", now),
        ("test-viewer-uid", "viewer@veteran-signals.com", "Test Viewer", "viewer", now),
    ]

    test_db.executemany(
        "INSERT INTO users (user_id, email, display_name, role, created_at) VALUES (?, ?, ?, ?, ?)",
        users,
    )
    test_db.commit()
    return test_db
