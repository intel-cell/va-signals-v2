#!/usr/bin/env python3
"""
Migration: Add compound_signals table for cross-source correlation engine.

Run with: python -m migrations.008_add_compound_signals
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db import connect, execute


def run_migration():
    """Create compound_signals table and indexes."""
    print("Running migration 008: Add compound_signals table...")

    con = connect()
    try:
        execute(con, """
            CREATE TABLE IF NOT EXISTS compound_signals (
                compound_id TEXT PRIMARY KEY,
                rule_id TEXT NOT NULL,
                severity_score REAL NOT NULL,
                narrative TEXT,
                temporal_window_hours INTEGER,
                member_events TEXT NOT NULL,
                topics TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                resolved_at TEXT,
                UNIQUE(rule_id, compound_id)
            )
        """)
        con.commit()
        print("  OK: Created compound_signals table")

        execute(con, """
            CREATE INDEX IF NOT EXISTS idx_compound_signals_rule
            ON compound_signals(rule_id)
        """)
        execute(con, """
            CREATE INDEX IF NOT EXISTS idx_compound_signals_created
            ON compound_signals(created_at)
        """)
        execute(con, """
            CREATE INDEX IF NOT EXISTS idx_compound_signals_severity
            ON compound_signals(severity_score)
        """)
        con.commit()
        print("  OK: Created indexes")

    except Exception as e:
        con.rollback()
        print(f"\nMigration failed: {e}")
        raise
    finally:
        con.close()

    print("\nMigration 008 complete.")


if __name__ == "__main__":
    run_migration()
