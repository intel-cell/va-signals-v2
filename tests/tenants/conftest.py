"""Shared fixtures for multi-tenant tests."""

import pytest

from src.db import connect, execute
from src.tenants.manager import TenantManager
from src.tenants.models import TenantContext, TenantCreateRequest, TenantPlan, TenantSettings


@pytest.fixture
def manager():
    """Fresh TenantManager instance."""
    return TenantManager()


@pytest.fixture
def sample_create_request():
    """Standard tenant creation request."""
    return TenantCreateRequest(
        name="Test Org",
        slug="test-org",
        billing_email="test@example.com",
        plan=TenantPlan.STARTER,
    )


@pytest.fixture
def _seed_owner_user():
    """Insert a test owner user into the users table."""
    con = connect()
    execute(
        con,
        "INSERT OR IGNORE INTO users (user_id, email, display_name, role, created_at) "
        "VALUES (:uid, :email, :name, :role, :created_at)",
        {
            "uid": "owner-001",
            "email": "owner@test.com",
            "name": "Owner",
            "role": "commander",
            "created_at": "2024-01-01T00:00:00",
        },
    )
    con.commit()
    con.close()


@pytest.fixture
def created_tenant(manager, sample_create_request, _seed_owner_user):
    """A fully created tenant with owner membership and settings."""
    return manager.create_tenant(sample_create_request, "owner-001")


@pytest.fixture
def _seed_extra_users():
    """Insert additional test users for member operations."""
    con = connect()
    users = [
        ("user-002", "member2@test.com", "Member Two", "analyst", "2024-01-01T00:00:00"),
        ("user-003", "member3@test.com", "Member Three", "viewer", "2024-01-01T00:00:00"),
        ("user-004", "member4@test.com", "Member Four", "leadership", "2024-01-01T00:00:00"),
    ]
    for uid, email, name, role, ts in users:
        execute(
            con,
            "INSERT OR IGNORE INTO users (user_id, email, display_name, role, created_at) "
            "VALUES (:uid, :email, :name, :role, :created_at)",
            {"uid": uid, "email": email, "name": name, "role": role, "created_at": ts},
        )
    con.commit()
    con.close()


@pytest.fixture
def sample_settings():
    """A TenantSettings instance for context tests."""
    return TenantSettings(
        tenant_id="tenant-abc",
        api_rate_limit_per_minute=60,
        api_rate_limit_per_day=10000,
        enable_websocket=True,
        enable_battlefield=True,
        enable_oversight=True,
        enable_state_intelligence=True,
        enable_ml_scoring=False,
        enable_custom_integrations=False,
    )


@pytest.fixture
def sample_context(sample_settings):
    """A TenantContext with settings attached."""
    return TenantContext(
        tenant_id="tenant-abc",
        tenant_name="Test Org",
        tenant_slug="test-org",
        plan=TenantPlan.STARTER,
        user_id="owner-001",
        user_role="commander",
        settings=sample_settings,
    )
