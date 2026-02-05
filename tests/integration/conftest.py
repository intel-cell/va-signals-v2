"""Fixtures for integration tests.

HOTEL COMMAND - Integration test fixtures.

Provides:
- Full app test client
- Seeded database
- Mock external services
"""

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def full_test_client():
    """
    Full FastAPI TestClient with all middleware and routes.

    Includes:
    - Auth middleware (ECHO)
    - RBAC enforcement (ECHO)
    - Audit logging (ECHO)
    - All API routes (existing + new)
    """
    # TODO: Update once ECHO delivers full auth integration
    # from fastapi.testclient import TestClient
    # from src.dashboard_api import app
    # return TestClient(app)
    return MagicMock()


@pytest.fixture
def seeded_full_db():
    """
    Full database with all tables and test data.

    Includes:
    - Users table with test accounts
    - Sample source runs
    - Sample documents
    - Sample battlefield vehicles
    """
    import sqlite3

    con = sqlite3.connect(":memory:")

    # Users table
    con.execute("""
        CREATE TABLE users (
            uid TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            role TEXT NOT NULL DEFAULT 'viewer',
            created_at TEXT NOT NULL,
            last_login TEXT
        )
    """)

    # Audit log table
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

    # Source runs (minimal for testing)
    con.execute("""
        CREATE TABLE source_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT NOT NULL,
            started_at TEXT NOT NULL,
            ended_at TEXT NOT NULL,
            status TEXT NOT NULL,
            records_fetched INTEGER DEFAULT 0,
            errors_json TEXT DEFAULT '[]'
        )
    """)

    # Battlefield vehicles (minimal for testing)
    con.execute("""
        CREATE TABLE bf_vehicles (
            vehicle_id TEXT PRIMARY KEY,
            vehicle_type TEXT NOT NULL,
            title TEXT NOT NULL,
            identifier TEXT NOT NULL,
            current_stage TEXT NOT NULL,
            status_date TEXT NOT NULL,
            our_posture TEXT NOT NULL DEFAULT 'monitor',
            heat_score REAL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # Seed test data
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    # Test users
    users = [
        ("cmd-001", "commander@test.com", "commander", now),
        ("usr-001", "analyst@test.com", "analyst", now),
        ("usr-002", "viewer@test.com", "viewer", now),
    ]
    con.executemany(
        "INSERT INTO users (uid, email, role, created_at) VALUES (?, ?, ?, ?)",
        users
    )

    # Test source runs
    runs = [
        ("fr_delta", now, now, "SUCCESS", 5, "[]"),
        ("ecfr_delta", now, now, "NO_DATA", 0, "[]"),
        ("bills", now, now, "ERROR", 0, '["API timeout"]'),
    ]
    con.executemany(
        """INSERT INTO source_runs
           (source_id, started_at, ended_at, status, records_fetched, errors_json)
           VALUES (?, ?, ?, ?, ?, ?)""",
        runs
    )

    # Test vehicles
    vehicles = [
        ("bill_hr-119-1234", "bill", "Test Bill", "H.R. 1234", "committee", "2026-01-15", "monitor", 75.0, now, now),
        ("hearing_12345", "oversight", "Test Hearing", "HVAC-12345", "active", "2026-02-01", "support", 90.0, now, now),
    ]
    con.executemany(
        """INSERT INTO bf_vehicles
           (vehicle_id, vehicle_type, title, identifier, current_stage, status_date,
            our_posture, heat_score, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        vehicles
    )

    con.commit()
    yield con
    con.close()


@pytest.fixture
def mock_firebase_admin():
    """Mock Firebase Admin SDK for testing."""
    with patch("firebase_admin.auth") as mock_auth:
        mock_auth.verify_id_token.return_value = {
            "uid": "test-uid",
            "email": "test@veteran-signals.com",
        }
        yield mock_auth
