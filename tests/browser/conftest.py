"""Pytest fixtures for Playwright browser tests.

Provides browser lifecycle, auth bypass via session cookie injection,
and role-specific page fixtures for RBAC testing.

IMPORTANT: Browser tests run against a live server, so we override the
autouse use_test_db fixture from tests/conftest.py (which monkeypatches
DB_PATH for unit tests). The server has its own database.

ARCHITECTURE: Browser contexts are session-scoped (one per auth role)
to avoid exhausting TCP connections. Each test gets a fresh page (tab)
within the shared context. This limits total contexts to 2 (unauth +
commander) instead of creating one per test.
"""

import sys
from datetime import UTC
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

# Ensure project root is on sys.path for src imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

BASE_URL = "http://localhost:8000"


# ---------------------------------------------------------------------------
# Override parent autouse fixture — browser tests use the server's DB
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def use_test_db():
    """No-op override: browser tests use the live server's database."""
    yield


# ---------------------------------------------------------------------------
# Session-scoped: browser + test user seeding
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def _seed_test_users():
    """Seed test users into the server's database for auth bypass testing."""
    from datetime import datetime

    from src.db import connect, execute, init_db

    init_db()
    con = connect()
    now = datetime.now(UTC).isoformat()

    test_users = [
        ("test-commander-uid", "commander@test.dev", "commander"),
        ("test-analyst-uid", "analyst@test.dev", "analyst"),
        ("test-viewer-uid", "viewer@test.dev", "viewer"),
    ]
    for uid, email, role in test_users:
        execute(
            con,
            """INSERT OR IGNORE INTO users (user_id, email, role, created_at)
               VALUES (:uid, :email, :role, :now)""",
            {"uid": uid, "email": email, "role": role, "now": now},
        )
    con.commit()
    con.close()


@pytest.fixture(scope="session")
def browser(_seed_test_users):
    """Launch headless Chromium for the entire test session."""
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


# ---------------------------------------------------------------------------
# Auth cookie helpers
# ---------------------------------------------------------------------------


def _make_session_cookie(user_id, email):
    """Create an HMAC-signed session token using the dev secret."""
    from src.auth.firebase_config import create_session_token

    token = create_session_token(user_id, email, expires_in_hours=1)
    return [
        {"name": "va_signals_session", "value": token, "domain": "localhost", "path": "/"},
        {"name": "csrf_token", "value": "test-csrf-token", "domain": "localhost", "path": "/"},
    ]


# ---------------------------------------------------------------------------
# Session-scoped contexts — minimized to 2 to prevent connection exhaustion
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def _unauth_context(browser):
    """Shared unauthenticated browser context (session-scoped)."""
    ctx = browser.new_context(viewport={"width": 1920, "height": 1080})
    yield ctx
    ctx.close()


@pytest.fixture(scope="session")
def _commander_context(browser):
    """Shared commander-auth browser context (session-scoped)."""
    ctx = browser.new_context(viewport={"width": 1920, "height": 1080})
    ctx.add_cookies(_make_session_cookie("test-commander-uid", "commander@test.dev"))
    yield ctx
    ctx.close()


# ---------------------------------------------------------------------------
# Per-test page fixtures — fresh tab in shared context
# ---------------------------------------------------------------------------


@pytest.fixture
def page(_unauth_context):
    """Unauthenticated browser page (fresh tab in shared context)."""
    pg = _unauth_context.new_page()
    yield pg
    pg.close()


@pytest.fixture
def authenticated_page(_commander_context):
    """Page with commander-level session cookie pre-injected."""
    pg = _commander_context.new_page()
    yield pg
    pg.close()
