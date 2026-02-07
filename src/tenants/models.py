"""
Tenant data models for multi-tenant support.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class TenantPlan(str, Enum):
    """Subscription plans for tenants."""

    FREE = "free"  # Limited features, rate limited
    STARTER = "starter"  # Small team, basic features
    PROFESSIONAL = "professional"  # Full features, priority support
    ENTERPRISE = "enterprise"  # Custom limits, dedicated support


class TenantStatus(str, Enum):
    """Tenant lifecycle status."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    TRIAL = "trial"
    CANCELLED = "cancelled"


class Tenant(BaseModel):
    """Organization/tenant model."""

    tenant_id: str
    name: str
    slug: str  # URL-safe identifier
    plan: TenantPlan = TenantPlan.FREE
    status: TenantStatus = TenantStatus.ACTIVE
    created_at: datetime
    updated_at: datetime
    owner_user_id: str
    billing_email: str | None = None
    domain: str | None = None  # Optional custom domain
    trial_ends_at: datetime | None = None
    features_json: str | None = None  # Enabled features override


class TenantSettings(BaseModel):
    """Tenant-specific configuration."""

    tenant_id: str

    # Rate limits
    api_rate_limit_per_minute: int = 60
    api_rate_limit_per_day: int = 10000
    max_users: int = 5
    max_signals_per_day: int = 1000

    # Feature flags
    enable_websocket: bool = True
    enable_battlefield: bool = True
    enable_oversight: bool = True
    enable_state_intelligence: bool = True
    enable_ml_scoring: bool = False
    enable_custom_integrations: bool = False

    # Notification settings
    slack_webhook_url: str | None = None
    email_notifications_enabled: bool = True
    daily_digest_enabled: bool = True

    # Retention
    data_retention_days: int = 90
    audit_log_retention_days: int = 365

    # Branding
    logo_url: str | None = None
    primary_color: str | None = None

    created_at: datetime | None = None
    updated_at: datetime | None = None


class TenantMember(BaseModel):
    """User membership in a tenant."""

    user_id: str
    tenant_id: str
    role: str  # Uses existing UserRole enum values
    joined_at: datetime
    invited_by: str | None = None
    is_primary: bool = False  # Primary tenant for user


class TenantContext(BaseModel):
    """
    Runtime context for tenant-scoped operations.

    This is passed through middleware and available in request handlers
    to ensure all queries are properly scoped.
    """

    tenant_id: str
    tenant_name: str
    tenant_slug: str
    plan: TenantPlan
    user_id: str
    user_role: str
    settings: TenantSettings | None = None

    def has_feature(self, feature: str) -> bool:
        """Check if tenant has a specific feature enabled."""
        if not self.settings:
            return False
        return getattr(self.settings, f"enable_{feature}", False)

    def within_rate_limit(self, current_count: int, limit_type: str = "minute") -> bool:
        """Check if current usage is within rate limits."""
        if not self.settings:
            return True
        if limit_type == "minute":
            return current_count < self.settings.api_rate_limit_per_minute
        elif limit_type == "day":
            return current_count < self.settings.api_rate_limit_per_day
        return True


# Request/Response models for API


class TenantCreateRequest(BaseModel):
    """Request to create a new tenant."""

    name: str = Field(..., min_length=2, max_length=100)
    slug: str = Field(..., min_length=2, max_length=50, pattern=r"^[a-z0-9-]+$")
    billing_email: str | None = None
    domain: str | None = None
    plan: TenantPlan = TenantPlan.FREE


class TenantUpdateRequest(BaseModel):
    """Request to update tenant details."""

    name: str | None = Field(None, min_length=2, max_length=100)
    billing_email: str | None = None
    domain: str | None = None
    plan: TenantPlan | None = None
    status: TenantStatus | None = None


class TenantInviteRequest(BaseModel):
    """Request to invite a user to a tenant."""

    email: str
    role: str = "viewer"


class TenantResponse(BaseModel):
    """Tenant details response."""

    tenant_id: str
    name: str
    slug: str
    plan: str
    status: str
    created_at: str
    member_count: int
    owner_email: str | None = None


class TenantMemberResponse(BaseModel):
    """Tenant member response."""

    user_id: str
    email: str
    display_name: str | None = None
    role: str
    joined_at: str
    is_primary: bool
