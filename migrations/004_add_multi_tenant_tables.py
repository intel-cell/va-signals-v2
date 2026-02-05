#!/usr/bin/env python3
"""
Migration: Add multi-tenant support tables.

Creates tables for:
- tenants: Organization/tenant records
- tenant_settings: Tenant-specific configuration
- tenant_members: User membership in tenants

Run with: python -m migrations.004_add_multi_tenant_tables
"""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db import connect, execute

MULTI_TENANT_TABLES = [
    # Tenants table
    """
    CREATE TABLE IF NOT EXISTS tenants (
        tenant_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        plan TEXT NOT NULL DEFAULT 'free',
        status TEXT NOT NULL DEFAULT 'active',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        owner_user_id TEXT NOT NULL,
        billing_email TEXT,
        domain TEXT,
        trial_ends_at TEXT,
        features_json TEXT,
        CONSTRAINT valid_plan CHECK (plan IN ('free', 'starter', 'professional', 'enterprise')),
        CONSTRAINT valid_status CHECK (status IN ('active', 'suspended', 'trial', 'cancelled'))
    )
    """,

    # Tenant settings table
    """
    CREATE TABLE IF NOT EXISTS tenant_settings (
        tenant_id TEXT PRIMARY KEY REFERENCES tenants(tenant_id),
        api_rate_limit_per_minute INTEGER NOT NULL DEFAULT 60,
        api_rate_limit_per_day INTEGER NOT NULL DEFAULT 10000,
        max_users INTEGER NOT NULL DEFAULT 5,
        max_signals_per_day INTEGER NOT NULL DEFAULT 1000,
        enable_websocket BOOLEAN DEFAULT TRUE,
        enable_battlefield BOOLEAN DEFAULT TRUE,
        enable_oversight BOOLEAN DEFAULT TRUE,
        enable_state_intelligence BOOLEAN DEFAULT TRUE,
        enable_ml_scoring BOOLEAN DEFAULT FALSE,
        enable_custom_integrations BOOLEAN DEFAULT FALSE,
        slack_webhook_url TEXT,
        email_notifications_enabled BOOLEAN DEFAULT TRUE,
        daily_digest_enabled BOOLEAN DEFAULT TRUE,
        data_retention_days INTEGER NOT NULL DEFAULT 90,
        audit_log_retention_days INTEGER NOT NULL DEFAULT 365,
        logo_url TEXT,
        primary_color TEXT,
        created_at TEXT,
        updated_at TEXT
    )
    """,

    # Tenant members table
    """
    CREATE TABLE IF NOT EXISTS tenant_members (
        user_id TEXT NOT NULL,
        tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
        role TEXT NOT NULL DEFAULT 'viewer',
        joined_at TEXT NOT NULL,
        invited_by TEXT,
        is_primary BOOLEAN DEFAULT FALSE,
        PRIMARY KEY (user_id, tenant_id),
        CONSTRAINT valid_role CHECK (role IN ('commander', 'leadership', 'analyst', 'viewer'))
    )
    """,

    # Indexes
    "CREATE INDEX IF NOT EXISTS idx_tenants_slug ON tenants(slug)",
    "CREATE INDEX IF NOT EXISTS idx_tenants_owner ON tenants(owner_user_id)",
    "CREATE INDEX IF NOT EXISTS idx_tenants_status ON tenants(status)",
    "CREATE INDEX IF NOT EXISTS idx_tenant_members_tenant ON tenant_members(tenant_id)",
    "CREATE INDEX IF NOT EXISTS idx_tenant_members_user ON tenant_members(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_tenant_members_primary ON tenant_members(is_primary)",
]

# Add tenant_id column to key tables for data isolation
TENANT_COLUMN_MIGRATIONS = [
    # These ALTER TABLE statements add tenant_id to existing tables
    # In production, this would need careful data migration

    # Signals
    "ALTER TABLE state_signals ADD COLUMN IF NOT EXISTS tenant_id TEXT",
    "CREATE INDEX IF NOT EXISTS idx_state_signals_tenant ON state_signals(tenant_id)",

    # Oversight events
    "ALTER TABLE om_events ADD COLUMN IF NOT EXISTS tenant_id TEXT",
    "CREATE INDEX IF NOT EXISTS idx_om_events_tenant ON om_events(tenant_id)",

    # Battlefield vehicles
    "ALTER TABLE bf_vehicles ADD COLUMN IF NOT EXISTS tenant_id TEXT",
    "CREATE INDEX IF NOT EXISTS idx_bf_vehicles_tenant ON bf_vehicles(tenant_id)",

    # Evidence packs
    "ALTER TABLE evidence_packs ADD COLUMN IF NOT EXISTS tenant_id TEXT",
    "CREATE INDEX IF NOT EXISTS idx_evidence_packs_tenant ON evidence_packs(tenant_id)",

    # Impact memos
    "ALTER TABLE impact_memos ADD COLUMN IF NOT EXISTS tenant_id TEXT",
    "CREATE INDEX IF NOT EXISTS idx_impact_memos_tenant ON impact_memos(tenant_id)",

    # CEO briefs
    "ALTER TABLE ceo_briefs ADD COLUMN IF NOT EXISTS tenant_id TEXT",
    "CREATE INDEX IF NOT EXISTS idx_ceo_briefs_tenant ON ceo_briefs(tenant_id)",

    # Audit log
    "ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS tenant_id TEXT",
    "CREATE INDEX IF NOT EXISTS idx_audit_log_tenant ON audit_log(tenant_id)",
]


def run_migration():
    """Run the multi-tenant migration."""
    print("Running multi-tenant migration...")

    con = connect()
    try:
        # Create core tenant tables
        print("\nCreating tenant tables...")
        for sql in MULTI_TENANT_TABLES:
            try:
                execute(con, sql)
                print(f"  ✓ Executed: {sql[:60]}...")
            except Exception as e:
                print(f"  ⚠ Warning: {e}")

        # Add tenant_id columns to existing tables
        print("\nAdding tenant_id columns to existing tables...")
        for sql in TENANT_COLUMN_MIGRATIONS:
            try:
                execute(con, sql)
                print(f"  ✓ Executed: {sql[:60]}...")
            except Exception as e:
                # ALTER TABLE IF NOT EXISTS might fail on some DBs
                if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                    print(f"  - Skipped (already exists): {sql[:50]}...")
                else:
                    print(f"  ⚠ Warning: {e}")

        con.commit()
        print("\n✅ Multi-tenant migration completed successfully!")

    except Exception as e:
        con.rollback()
        print(f"\n❌ Migration failed: {e}")
        raise
    finally:
        con.close()


def create_default_tenant(owner_user_id: str = "pending-commander"):
    """Create a default tenant for existing data."""
    print("\nCreating default tenant...")

    con = connect()
    try:
        # Check if default tenant exists
        cur = execute(
            con,
            "SELECT tenant_id FROM tenants WHERE slug = 'default'"
        )
        if cur.fetchone():
            print("  - Default tenant already exists")
            return

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()

        # Create default tenant
        execute(
            con,
            """
            INSERT INTO tenants (
                tenant_id, name, slug, plan, status,
                created_at, updated_at, owner_user_id
            ) VALUES (
                'tenant_default', 'VetClaims.ai', 'default', 'enterprise', 'active',
                :now, :now, :owner
            )
            """,
            {"now": now, "owner": owner_user_id}
        )

        # Create settings
        execute(
            con,
            """
            INSERT INTO tenant_settings (
                tenant_id, api_rate_limit_per_minute, api_rate_limit_per_day,
                max_users, max_signals_per_day, enable_ml_scoring,
                enable_custom_integrations, data_retention_days,
                created_at, updated_at
            ) VALUES (
                'tenant_default', 500, 100000, 999, 50000, TRUE, TRUE, 730,
                :now, :now
            )
            """,
            {"now": now}
        )

        # Add owner as member
        execute(
            con,
            """
            INSERT INTO tenant_members (
                user_id, tenant_id, role, joined_at, is_primary
            ) VALUES (
                :owner, 'tenant_default', 'commander', :now, TRUE
            )
            """,
            {"owner": owner_user_id, "now": now}
        )

        # Update existing data with default tenant
        print("  Updating existing data with default tenant...")
        tables = [
            "state_signals", "om_events", "bf_vehicles",
            "evidence_packs", "impact_memos", "ceo_briefs", "audit_log"
        ]
        for table in tables:
            try:
                execute(
                    con,
                    f"UPDATE {table} SET tenant_id = 'tenant_default' WHERE tenant_id IS NULL"
                )
                print(f"    ✓ Updated {table}")
            except Exception as e:
                print(f"    - Skipped {table}: {e}")

        con.commit()
        print("  ✓ Default tenant created")

    except Exception as e:
        con.rollback()
        print(f"  ✗ Failed: {e}")
    finally:
        con.close()


if __name__ == "__main__":
    run_migration()
    create_default_tenant()
