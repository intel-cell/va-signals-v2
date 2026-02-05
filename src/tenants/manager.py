"""
Tenant management operations.

Handles tenant CRUD, membership, and settings management.
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from ..db import connect, execute
from .models import (
    Tenant,
    TenantSettings,
    TenantMember,
    TenantPlan,
    TenantStatus,
    TenantCreateRequest,
    TenantUpdateRequest,
)

logger = logging.getLogger(__name__)


class TenantManager:
    """
    Manages tenant lifecycle and membership.

    Provides methods for creating, updating, and querying tenants,
    as well as managing user memberships within tenants.
    """

    def create_tenant(
        self,
        request: TenantCreateRequest,
        owner_user_id: str,
    ) -> Tenant:
        """
        Create a new tenant organization.

        Args:
            request: Tenant creation request
            owner_user_id: User ID of the tenant owner

        Returns:
            Created Tenant object
        """
        tenant_id = f"tenant_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        con = connect()
        try:
            # Create tenant
            execute(
                con,
                """
                INSERT INTO tenants (
                    tenant_id, name, slug, plan, status,
                    created_at, updated_at, owner_user_id,
                    billing_email, domain
                ) VALUES (
                    :tenant_id, :name, :slug, :plan, :status,
                    :created_at, :updated_at, :owner_user_id,
                    :billing_email, :domain
                )
                """,
                {
                    "tenant_id": tenant_id,
                    "name": request.name,
                    "slug": request.slug,
                    "plan": request.plan.value,
                    "status": TenantStatus.ACTIVE.value,
                    "created_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                    "owner_user_id": owner_user_id,
                    "billing_email": request.billing_email,
                    "domain": request.domain,
                }
            )

            # Create default settings
            self._create_default_settings(con, tenant_id, request.plan)

            # Add owner as member with commander role
            execute(
                con,
                """
                INSERT INTO tenant_members (
                    user_id, tenant_id, role, joined_at, is_primary
                ) VALUES (
                    :user_id, :tenant_id, :role, :joined_at, :is_primary
                )
                """,
                {
                    "user_id": owner_user_id,
                    "tenant_id": tenant_id,
                    "role": "commander",
                    "joined_at": now.isoformat(),
                    "is_primary": True,
                }
            )

            con.commit()
            logger.info(f"Created tenant {tenant_id} ({request.name})")

            return Tenant(
                tenant_id=tenant_id,
                name=request.name,
                slug=request.slug,
                plan=request.plan,
                status=TenantStatus.ACTIVE,
                created_at=now,
                updated_at=now,
                owner_user_id=owner_user_id,
                billing_email=request.billing_email,
                domain=request.domain,
            )

        except Exception as e:
            con.rollback()
            logger.error(f"Failed to create tenant: {e}")
            raise
        finally:
            con.close()

    def _create_default_settings(
        self,
        con,
        tenant_id: str,
        plan: TenantPlan
    ) -> None:
        """Create default settings based on plan."""
        # Plan-specific defaults
        plan_settings = {
            TenantPlan.FREE: {
                "api_rate_limit_per_minute": 30,
                "api_rate_limit_per_day": 1000,
                "max_users": 2,
                "max_signals_per_day": 100,
                "enable_ml_scoring": False,
                "enable_custom_integrations": False,
                "data_retention_days": 30,
            },
            TenantPlan.STARTER: {
                "api_rate_limit_per_minute": 60,
                "api_rate_limit_per_day": 5000,
                "max_users": 5,
                "max_signals_per_day": 500,
                "enable_ml_scoring": False,
                "enable_custom_integrations": False,
                "data_retention_days": 90,
            },
            TenantPlan.PROFESSIONAL: {
                "api_rate_limit_per_minute": 120,
                "api_rate_limit_per_day": 20000,
                "max_users": 25,
                "max_signals_per_day": 2000,
                "enable_ml_scoring": True,
                "enable_custom_integrations": True,
                "data_retention_days": 365,
            },
            TenantPlan.ENTERPRISE: {
                "api_rate_limit_per_minute": 500,
                "api_rate_limit_per_day": 100000,
                "max_users": 999,
                "max_signals_per_day": 50000,
                "enable_ml_scoring": True,
                "enable_custom_integrations": True,
                "data_retention_days": 730,
            },
        }

        settings = plan_settings.get(plan, plan_settings[TenantPlan.FREE])
        now = datetime.now(timezone.utc).isoformat()

        execute(
            con,
            """
            INSERT INTO tenant_settings (
                tenant_id, api_rate_limit_per_minute, api_rate_limit_per_day,
                max_users, max_signals_per_day, enable_ml_scoring,
                enable_custom_integrations, data_retention_days,
                created_at, updated_at
            ) VALUES (
                :tenant_id, :rate_minute, :rate_day,
                :max_users, :max_signals, :enable_ml,
                :enable_custom, :retention,
                :created_at, :updated_at
            )
            """,
            {
                "tenant_id": tenant_id,
                "rate_minute": settings["api_rate_limit_per_minute"],
                "rate_day": settings["api_rate_limit_per_day"],
                "max_users": settings["max_users"],
                "max_signals": settings["max_signals_per_day"],
                "enable_ml": settings["enable_ml_scoring"],
                "enable_custom": settings["enable_custom_integrations"],
                "retention": settings["data_retention_days"],
                "created_at": now,
                "updated_at": now,
            }
        )

    def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """Get tenant by ID."""
        con = connect()
        try:
            cur = execute(
                con,
                """
                SELECT tenant_id, name, slug, plan, status,
                       created_at, updated_at, owner_user_id,
                       billing_email, domain, trial_ends_at
                FROM tenants
                WHERE tenant_id = :tenant_id
                """,
                {"tenant_id": tenant_id}
            )
            row = cur.fetchone()
            if not row:
                return None

            return Tenant(
                tenant_id=row[0],
                name=row[1],
                slug=row[2],
                plan=TenantPlan(row[3]),
                status=TenantStatus(row[4]),
                created_at=datetime.fromisoformat(row[5]),
                updated_at=datetime.fromisoformat(row[6]),
                owner_user_id=row[7],
                billing_email=row[8],
                domain=row[9],
                trial_ends_at=datetime.fromisoformat(row[10]) if row[10] else None,
            )
        finally:
            con.close()

    def get_tenant_by_slug(self, slug: str) -> Optional[Tenant]:
        """Get tenant by URL slug."""
        con = connect()
        try:
            cur = execute(
                con,
                "SELECT tenant_id FROM tenants WHERE slug = :slug",
                {"slug": slug}
            )
            row = cur.fetchone()
            if not row:
                return None
            return self.get_tenant(row[0])
        finally:
            con.close()

    def get_tenant_settings(self, tenant_id: str) -> Optional[TenantSettings]:
        """Get tenant settings."""
        con = connect()
        try:
            cur = execute(
                con,
                """
                SELECT tenant_id, api_rate_limit_per_minute, api_rate_limit_per_day,
                       max_users, max_signals_per_day, enable_websocket,
                       enable_battlefield, enable_oversight, enable_state_intelligence,
                       enable_ml_scoring, enable_custom_integrations,
                       slack_webhook_url, email_notifications_enabled,
                       daily_digest_enabled, data_retention_days,
                       audit_log_retention_days, logo_url, primary_color,
                       created_at, updated_at
                FROM tenant_settings
                WHERE tenant_id = :tenant_id
                """,
                {"tenant_id": tenant_id}
            )
            row = cur.fetchone()
            if not row:
                return None

            return TenantSettings(
                tenant_id=row[0],
                api_rate_limit_per_minute=row[1],
                api_rate_limit_per_day=row[2],
                max_users=row[3],
                max_signals_per_day=row[4],
                enable_websocket=bool(row[5]),
                enable_battlefield=bool(row[6]),
                enable_oversight=bool(row[7]),
                enable_state_intelligence=bool(row[8]),
                enable_ml_scoring=bool(row[9]),
                enable_custom_integrations=bool(row[10]),
                slack_webhook_url=row[11],
                email_notifications_enabled=bool(row[12]),
                daily_digest_enabled=bool(row[13]),
                data_retention_days=row[14],
                audit_log_retention_days=row[15],
                logo_url=row[16],
                primary_color=row[17],
                created_at=datetime.fromisoformat(row[18]) if row[18] else None,
                updated_at=datetime.fromisoformat(row[19]) if row[19] else None,
            )
        finally:
            con.close()

    def get_user_tenants(self, user_id: str) -> list[dict]:
        """Get all tenants a user belongs to."""
        con = connect()
        try:
            cur = execute(
                con,
                """
                SELECT t.tenant_id, t.name, t.slug, t.plan, t.status,
                       tm.role, tm.is_primary
                FROM tenants t
                JOIN tenant_members tm ON t.tenant_id = tm.tenant_id
                WHERE tm.user_id = :user_id
                ORDER BY tm.is_primary DESC, t.name
                """,
                {"user_id": user_id}
            )
            return [
                {
                    "tenant_id": row[0],
                    "name": row[1],
                    "slug": row[2],
                    "plan": row[3],
                    "status": row[4],
                    "role": row[5],
                    "is_primary": bool(row[6]),
                }
                for row in cur.fetchall()
            ]
        finally:
            con.close()

    def get_tenant_members(self, tenant_id: str) -> list[dict]:
        """Get all members of a tenant."""
        con = connect()
        try:
            cur = execute(
                con,
                """
                SELECT tm.user_id, u.email, u.display_name, tm.role,
                       tm.joined_at, tm.is_primary
                FROM tenant_members tm
                JOIN users u ON tm.user_id = u.user_id
                WHERE tm.tenant_id = :tenant_id
                ORDER BY tm.is_primary DESC, tm.joined_at
                """,
                {"tenant_id": tenant_id}
            )
            return [
                {
                    "user_id": row[0],
                    "email": row[1],
                    "display_name": row[2],
                    "role": row[3],
                    "joined_at": row[4],
                    "is_primary": bool(row[5]),
                }
                for row in cur.fetchall()
            ]
        finally:
            con.close()

    def add_member(
        self,
        tenant_id: str,
        user_id: str,
        role: str,
        invited_by: Optional[str] = None
    ) -> TenantMember:
        """Add a user to a tenant."""
        con = connect()
        now = datetime.now(timezone.utc)
        try:
            execute(
                con,
                """
                INSERT INTO tenant_members (
                    user_id, tenant_id, role, joined_at, invited_by, is_primary
                ) VALUES (
                    :user_id, :tenant_id, :role, :joined_at, :invited_by, :is_primary
                )
                ON CONFLICT (user_id, tenant_id) DO UPDATE
                SET role = :role, invited_by = :invited_by
                """,
                {
                    "user_id": user_id,
                    "tenant_id": tenant_id,
                    "role": role,
                    "joined_at": now.isoformat(),
                    "invited_by": invited_by,
                    "is_primary": False,
                }
            )
            con.commit()
            logger.info(f"Added user {user_id} to tenant {tenant_id} with role {role}")

            return TenantMember(
                user_id=user_id,
                tenant_id=tenant_id,
                role=role,
                joined_at=now,
                invited_by=invited_by,
                is_primary=False,
            )
        except Exception as e:
            con.rollback()
            logger.error(f"Failed to add member: {e}")
            raise
        finally:
            con.close()

    def remove_member(self, tenant_id: str, user_id: str) -> bool:
        """Remove a user from a tenant."""
        con = connect()
        try:
            cur = execute(
                con,
                """
                DELETE FROM tenant_members
                WHERE tenant_id = :tenant_id AND user_id = :user_id
                AND is_primary = FALSE
                """,
                {"tenant_id": tenant_id, "user_id": user_id}
            )
            con.commit()
            removed = cur.rowcount > 0
            if removed:
                logger.info(f"Removed user {user_id} from tenant {tenant_id}")
            return removed
        finally:
            con.close()

    def update_member_role(
        self,
        tenant_id: str,
        user_id: str,
        new_role: str
    ) -> bool:
        """Update a member's role in a tenant."""
        con = connect()
        try:
            cur = execute(
                con,
                """
                UPDATE tenant_members
                SET role = :role
                WHERE tenant_id = :tenant_id AND user_id = :user_id
                """,
                {"tenant_id": tenant_id, "user_id": user_id, "role": new_role}
            )
            con.commit()
            return cur.rowcount > 0
        finally:
            con.close()

    def is_member(self, tenant_id: str, user_id: str) -> bool:
        """Check if user is a member of tenant."""
        con = connect()
        try:
            cur = execute(
                con,
                """
                SELECT 1 FROM tenant_members
                WHERE tenant_id = :tenant_id AND user_id = :user_id
                """,
                {"tenant_id": tenant_id, "user_id": user_id}
            )
            return cur.fetchone() is not None
        finally:
            con.close()

    def get_member_role(self, tenant_id: str, user_id: str) -> Optional[str]:
        """Get user's role in a tenant."""
        con = connect()
        try:
            cur = execute(
                con,
                """
                SELECT role FROM tenant_members
                WHERE tenant_id = :tenant_id AND user_id = :user_id
                """,
                {"tenant_id": tenant_id, "user_id": user_id}
            )
            row = cur.fetchone()
            return row[0] if row else None
        finally:
            con.close()


# Global singleton instance
tenant_manager = TenantManager()
