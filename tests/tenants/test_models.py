"""Tests for multi-tenant data models.

Covers enums, Pydantic models, validation, feature checks, and rate limits.
"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from src.tenants.models import (
    Tenant,
    TenantContext,
    TenantCreateRequest,
    TenantInviteRequest,
    TenantMember,
    TenantMemberResponse,
    TenantPlan,
    TenantResponse,
    TenantSettings,
    TenantStatus,
    TenantUpdateRequest,
)

# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestTenantPlanEnum:
    def test_plan_values(self):
        assert TenantPlan.FREE.value == "free"
        assert TenantPlan.STARTER.value == "starter"
        assert TenantPlan.PROFESSIONAL.value == "professional"
        assert TenantPlan.ENTERPRISE.value == "enterprise"

    def test_plan_count(self):
        assert len(TenantPlan) == 4

    def test_plan_from_value(self):
        assert TenantPlan("free") is TenantPlan.FREE
        assert TenantPlan("enterprise") is TenantPlan.ENTERPRISE


class TestTenantStatusEnum:
    def test_status_values(self):
        assert TenantStatus.ACTIVE.value == "active"
        assert TenantStatus.SUSPENDED.value == "suspended"
        assert TenantStatus.TRIAL.value == "trial"
        assert TenantStatus.CANCELLED.value == "cancelled"

    def test_status_count(self):
        assert len(TenantStatus) == 4


# ---------------------------------------------------------------------------
# Tenant model
# ---------------------------------------------------------------------------


class TestTenantModel:
    def test_create_tenant_all_fields(self):
        now = datetime.now()
        t = Tenant(
            tenant_id="t-1",
            name="Acme",
            slug="acme",
            plan=TenantPlan.PROFESSIONAL,
            status=TenantStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            owner_user_id="u-1",
            billing_email="bill@acme.com",
            domain="acme.example.com",
        )
        assert t.tenant_id == "t-1"
        assert t.plan == TenantPlan.PROFESSIONAL
        assert t.billing_email == "bill@acme.com"
        assert t.domain == "acme.example.com"
        assert t.trial_ends_at is None

    def test_tenant_defaults(self):
        now = datetime.now()
        t = Tenant(
            tenant_id="t-2",
            name="Default",
            slug="default",
            created_at=now,
            updated_at=now,
            owner_user_id="u-2",
        )
        assert t.plan == TenantPlan.FREE
        assert t.status == TenantStatus.ACTIVE
        assert t.billing_email is None
        assert t.domain is None
        assert t.features_json is None


# ---------------------------------------------------------------------------
# TenantSettings
# ---------------------------------------------------------------------------


class TestTenantSettingsModel:
    def test_defaults(self):
        s = TenantSettings(tenant_id="ts-1")
        assert s.api_rate_limit_per_minute == 60
        assert s.api_rate_limit_per_day == 10000
        assert s.max_users == 5
        assert s.max_signals_per_day == 1000
        assert s.enable_websocket is True
        assert s.enable_battlefield is True
        assert s.enable_oversight is True
        assert s.enable_state_intelligence is True
        assert s.enable_ml_scoring is False
        assert s.enable_custom_integrations is False
        assert s.email_notifications_enabled is True
        assert s.daily_digest_enabled is True
        assert s.data_retention_days == 90
        assert s.audit_log_retention_days == 365
        assert s.slack_webhook_url is None
        assert s.logo_url is None
        assert s.primary_color is None


# ---------------------------------------------------------------------------
# TenantMember
# ---------------------------------------------------------------------------


class TestTenantMemberModel:
    def test_create_member(self):
        now = datetime.now()
        m = TenantMember(
            user_id="u-1",
            tenant_id="t-1",
            role="analyst",
            joined_at=now,
            invited_by="u-0",
            is_primary=False,
        )
        assert m.role == "analyst"
        assert m.invited_by == "u-0"
        assert m.is_primary is False

    def test_member_defaults(self):
        now = datetime.now()
        m = TenantMember(user_id="u-1", tenant_id="t-1", role="viewer", joined_at=now)
        assert m.invited_by is None
        assert m.is_primary is False


# ---------------------------------------------------------------------------
# TenantContext feature and rate-limit checks
# ---------------------------------------------------------------------------


class TestTenantContext:
    def test_has_feature_enabled(self, sample_context):
        assert sample_context.has_feature("websocket") is True
        assert sample_context.has_feature("battlefield") is True

    def test_has_feature_disabled(self, sample_context):
        assert sample_context.has_feature("ml_scoring") is False
        assert sample_context.has_feature("custom_integrations") is False

    def test_has_feature_nonexistent(self, sample_context):
        assert sample_context.has_feature("nonexistent_feature") is False

    def test_has_feature_no_settings(self):
        ctx = TenantContext(
            tenant_id="t-1",
            tenant_name="No Settings",
            tenant_slug="no-settings",
            plan=TenantPlan.FREE,
            user_id="u-1",
            user_role="viewer",
            settings=None,
        )
        assert ctx.has_feature("websocket") is False

    def test_within_rate_limit_minute(self, sample_context):
        assert sample_context.within_rate_limit(30, "minute") is True
        assert sample_context.within_rate_limit(59, "minute") is True
        assert sample_context.within_rate_limit(60, "minute") is False
        assert sample_context.within_rate_limit(100, "minute") is False

    def test_within_rate_limit_day(self, sample_context):
        assert sample_context.within_rate_limit(5000, "day") is True
        assert sample_context.within_rate_limit(9999, "day") is True
        assert sample_context.within_rate_limit(10000, "day") is False

    def test_within_rate_limit_unknown_type(self, sample_context):
        # Unknown limit_type returns True
        assert sample_context.within_rate_limit(999999, "week") is True

    def test_within_rate_limit_no_settings(self):
        ctx = TenantContext(
            tenant_id="t-1",
            tenant_name="No Settings",
            tenant_slug="no-settings",
            plan=TenantPlan.FREE,
            user_id="u-1",
            user_role="viewer",
            settings=None,
        )
        assert ctx.within_rate_limit(999999, "minute") is True


# ---------------------------------------------------------------------------
# Request models validation
# ---------------------------------------------------------------------------


class TestTenantCreateRequest:
    def test_valid_request(self):
        r = TenantCreateRequest(name="My Org", slug="my-org")
        assert r.plan == TenantPlan.FREE
        assert r.billing_email is None

    def test_slug_pattern_valid(self):
        TenantCreateRequest(name="Valid", slug="abc-123")

    def test_slug_pattern_invalid_uppercase(self):
        with pytest.raises(ValidationError):
            TenantCreateRequest(name="Bad", slug="Bad-Slug")

    def test_slug_pattern_invalid_space(self):
        with pytest.raises(ValidationError):
            TenantCreateRequest(name="Bad", slug="bad slug")

    def test_name_too_short(self):
        with pytest.raises(ValidationError):
            TenantCreateRequest(name="A", slug="valid")

    def test_slug_too_short(self):
        with pytest.raises(ValidationError):
            TenantCreateRequest(name="Valid", slug="a")


class TestTenantUpdateRequest:
    def test_all_none(self):
        r = TenantUpdateRequest()
        assert r.name is None
        assert r.plan is None
        assert r.status is None

    def test_partial_update(self):
        r = TenantUpdateRequest(name="New Name", plan=TenantPlan.ENTERPRISE)
        assert r.name == "New Name"
        assert r.plan == TenantPlan.ENTERPRISE


class TestTenantInviteRequest:
    def test_defaults(self):
        r = TenantInviteRequest(email="new@test.com")
        assert r.role == "viewer"

    def test_custom_role(self):
        r = TenantInviteRequest(email="new@test.com", role="analyst")
        assert r.role == "analyst"


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class TestTenantResponse:
    def test_create_response(self):
        r = TenantResponse(
            tenant_id="t-1",
            name="Acme",
            slug="acme",
            plan="starter",
            status="active",
            created_at="2024-01-01T00:00:00",
            member_count=3,
        )
        assert r.member_count == 3
        assert r.owner_email is None

    def test_with_owner_email(self):
        r = TenantResponse(
            tenant_id="t-1",
            name="Acme",
            slug="acme",
            plan="free",
            status="active",
            created_at="2024-01-01T00:00:00",
            member_count=1,
            owner_email="owner@acme.com",
        )
        assert r.owner_email == "owner@acme.com"


class TestTenantMemberResponse:
    def test_create_response(self):
        r = TenantMemberResponse(
            user_id="u-1",
            email="user@test.com",
            display_name="User One",
            role="analyst",
            joined_at="2024-01-01T00:00:00",
            is_primary=True,
        )
        assert r.is_primary is True
        assert r.display_name == "User One"

    def test_no_display_name(self):
        r = TenantMemberResponse(
            user_id="u-2",
            email="user2@test.com",
            role="viewer",
            joined_at="2024-01-01T00:00:00",
            is_primary=False,
        )
        assert r.display_name is None
