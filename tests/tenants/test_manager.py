"""Tests for TenantManager — CRUD, membership, and settings.

All tests rely on the autouse ``use_test_db`` fixture from the root conftest
which provides a fresh temp SQLite database with WAL mode for every test.
"""

import pytest

from src.tenants.models import TenantCreateRequest, TenantPlan

# ---------------------------------------------------------------------------
# Tenant creation
# ---------------------------------------------------------------------------


class TestCreateTenant:
    def test_creates_tenant_record(self, manager, sample_create_request, _seed_owner_user):
        tenant = manager.create_tenant(sample_create_request, "owner-001")
        assert tenant.tenant_id.startswith("tenant_")
        assert tenant.name == "Test Org"
        assert tenant.slug == "test-org"
        assert tenant.plan == TenantPlan.STARTER
        assert tenant.owner_user_id == "owner-001"

    def test_creates_settings_for_tenant(self, manager, sample_create_request, _seed_owner_user):
        tenant = manager.create_tenant(sample_create_request, "owner-001")
        settings = manager.get_tenant_settings(tenant.tenant_id)
        assert settings is not None
        assert settings.tenant_id == tenant.tenant_id

    def test_creates_owner_membership(self, manager, sample_create_request, _seed_owner_user):
        tenant = manager.create_tenant(sample_create_request, "owner-001")
        assert manager.is_member(tenant.tenant_id, "owner-001") is True
        role = manager.get_member_role(tenant.tenant_id, "owner-001")
        assert role == "commander"

    def test_free_plan_settings(self, manager, _seed_owner_user):
        req = TenantCreateRequest(name="Free Org", slug="free-org", plan=TenantPlan.FREE)
        tenant = manager.create_tenant(req, "owner-001")
        settings = manager.get_tenant_settings(tenant.tenant_id)
        assert settings.api_rate_limit_per_minute == 30
        assert settings.api_rate_limit_per_day == 1000
        assert settings.max_users == 2
        assert settings.enable_ml_scoring is False
        assert settings.data_retention_days == 30

    def test_starter_plan_settings(self, manager, _seed_owner_user):
        req = TenantCreateRequest(name="Starter Org", slug="starter-org", plan=TenantPlan.STARTER)
        tenant = manager.create_tenant(req, "owner-001")
        settings = manager.get_tenant_settings(tenant.tenant_id)
        assert settings.api_rate_limit_per_minute == 60
        assert settings.max_users == 5
        assert settings.data_retention_days == 90

    def test_professional_plan_settings(self, manager, _seed_owner_user):
        req = TenantCreateRequest(name="Pro Org", slug="pro-org", plan=TenantPlan.PROFESSIONAL)
        tenant = manager.create_tenant(req, "owner-001")
        settings = manager.get_tenant_settings(tenant.tenant_id)
        assert settings.api_rate_limit_per_minute == 120
        assert settings.max_users == 25
        assert settings.enable_ml_scoring is True
        assert settings.enable_custom_integrations is True
        assert settings.data_retention_days == 365

    def test_enterprise_plan_settings(self, manager, _seed_owner_user):
        req = TenantCreateRequest(name="Ent Org", slug="ent-org", plan=TenantPlan.ENTERPRISE)
        tenant = manager.create_tenant(req, "owner-001")
        settings = manager.get_tenant_settings(tenant.tenant_id)
        assert settings.api_rate_limit_per_minute == 500
        assert settings.api_rate_limit_per_day == 100000
        assert settings.max_users == 999
        assert settings.data_retention_days == 730

    def test_duplicate_slug_raises(self, manager, sample_create_request, _seed_owner_user):
        manager.create_tenant(sample_create_request, "owner-001")
        with pytest.raises(Exception):  # noqa: B017
            manager.create_tenant(sample_create_request, "owner-001")


# ---------------------------------------------------------------------------
# Tenant retrieval
# ---------------------------------------------------------------------------


class TestGetTenant:
    def test_get_existing_tenant(self, manager, created_tenant):
        result = manager.get_tenant(created_tenant.tenant_id)
        assert result is not None
        assert result.name == "Test Org"
        assert result.slug == "test-org"

    def test_get_nonexistent_tenant(self, manager):
        result = manager.get_tenant("tenant_nonexistent")
        assert result is None

    def test_get_tenant_by_slug(self, manager, created_tenant):
        result = manager.get_tenant_by_slug("test-org")
        assert result is not None
        assert result.tenant_id == created_tenant.tenant_id

    def test_get_tenant_by_slug_nonexistent(self, manager):
        result = manager.get_tenant_by_slug("nope")
        assert result is None


# ---------------------------------------------------------------------------
# Settings retrieval
# ---------------------------------------------------------------------------


class TestGetTenantSettings:
    def test_settings_returned(self, manager, created_tenant):
        settings = manager.get_tenant_settings(created_tenant.tenant_id)
        assert settings is not None
        assert settings.tenant_id == created_tenant.tenant_id

    def test_settings_nonexistent(self, manager):
        settings = manager.get_tenant_settings("tenant_nope")
        assert settings is None


# ---------------------------------------------------------------------------
# User tenants
# ---------------------------------------------------------------------------


class TestGetUserTenants:
    def test_owner_sees_tenant(self, manager, created_tenant):
        tenants = manager.get_user_tenants("owner-001")
        assert len(tenants) == 1
        assert tenants[0]["tenant_id"] == created_tenant.tenant_id
        assert tenants[0]["role"] == "commander"
        assert tenants[0]["is_primary"] is True

    def test_no_tenants(self, manager):
        tenants = manager.get_user_tenants("user-unknown")
        assert tenants == []

    def test_multiple_tenants(self, manager, _seed_owner_user):
        req1 = TenantCreateRequest(name="Org A", slug="org-a", plan=TenantPlan.FREE)
        req2 = TenantCreateRequest(name="Org B", slug="org-b", plan=TenantPlan.STARTER)
        manager.create_tenant(req1, "owner-001")
        manager.create_tenant(req2, "owner-001")
        tenants = manager.get_user_tenants("owner-001")
        assert len(tenants) == 2


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------


class TestGetTenantMembers:
    def test_returns_owner(self, manager, created_tenant):
        members = manager.get_tenant_members(created_tenant.tenant_id)
        assert len(members) == 1
        assert members[0]["user_id"] == "owner-001"
        assert members[0]["role"] == "commander"
        assert members[0]["is_primary"] is True

    def test_empty_for_unknown_tenant(self, manager):
        members = manager.get_tenant_members("tenant_nope")
        assert members == []


class TestAddMember:
    def test_add_member(self, manager, created_tenant, _seed_extra_users):
        member = manager.add_member(created_tenant.tenant_id, "user-002", "analyst", "owner-001")
        assert member.user_id == "user-002"
        assert member.role == "analyst"
        assert member.is_primary is False
        assert member.invited_by == "owner-001"

    def test_member_appears_in_list(self, manager, created_tenant, _seed_extra_users):
        manager.add_member(created_tenant.tenant_id, "user-002", "analyst")
        members = manager.get_tenant_members(created_tenant.tenant_id)
        assert len(members) == 2

    def test_add_member_upsert(self, manager, created_tenant, _seed_extra_users):
        manager.add_member(created_tenant.tenant_id, "user-002", "analyst")
        manager.add_member(created_tenant.tenant_id, "user-002", "leadership")
        role = manager.get_member_role(created_tenant.tenant_id, "user-002")
        assert role == "leadership"


class TestRemoveMember:
    def test_remove_non_primary(self, manager, created_tenant, _seed_extra_users):
        manager.add_member(created_tenant.tenant_id, "user-002", "analyst")
        removed = manager.remove_member(created_tenant.tenant_id, "user-002")
        assert removed is True
        assert manager.is_member(created_tenant.tenant_id, "user-002") is False

    def test_remove_primary_fails(self, manager, created_tenant):
        removed = manager.remove_member(created_tenant.tenant_id, "owner-001")
        assert removed is False
        assert manager.is_member(created_tenant.tenant_id, "owner-001") is True

    def test_remove_nonexistent(self, manager, created_tenant):
        removed = manager.remove_member(created_tenant.tenant_id, "user-ghost")
        assert removed is False


class TestUpdateMemberRole:
    def test_update_role(self, manager, created_tenant, _seed_extra_users):
        manager.add_member(created_tenant.tenant_id, "user-002", "viewer")
        updated = manager.update_member_role(created_tenant.tenant_id, "user-002", "analyst")
        assert updated is True
        assert manager.get_member_role(created_tenant.tenant_id, "user-002") == "analyst"

    def test_update_nonexistent(self, manager, created_tenant):
        updated = manager.update_member_role(created_tenant.tenant_id, "ghost", "viewer")
        assert updated is False


class TestIsMember:
    def test_owner_is_member(self, manager, created_tenant):
        assert manager.is_member(created_tenant.tenant_id, "owner-001") is True

    def test_non_member(self, manager, created_tenant):
        assert manager.is_member(created_tenant.tenant_id, "stranger") is False


class TestGetMemberRole:
    def test_owner_role(self, manager, created_tenant):
        role = manager.get_member_role(created_tenant.tenant_id, "owner-001")
        assert role == "commander"

    def test_non_member_role(self, manager, created_tenant):
        role = manager.get_member_role(created_tenant.tenant_id, "stranger")
        assert role is None
