#!/usr/bin/env python3
"""
Migration: Add staleness_alerts table for tracking expected-but-missing signals.

Run with: python -m migrations.007_add_staleness_tables
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db import connect, execute


def run_migration():
    """Create staleness_alerts table."""
    print("Running migration 007: Add staleness_alerts table...")

    con = connect()
    try:
        execute(con, """
            CREATE TABLE IF NOT EXISTS staleness_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT NOT NULL,
                alert_type TEXT NOT NULL DEFAULT 'missing',
                expected_by TEXT,
                last_success_at TEXT,
                hours_overdue REAL,
                consecutive_failures INTEGER DEFAULT 0,
                severity TEXT NOT NULL,
                created_at TEXT NOT NULL,
                resolved_at TEXT
            )
        """)
        con.commit()
        print("  OK: Created staleness_alerts table")

    except Exception as e:
        con.rollback()
        print(f"\nMigration failed: {e}")
        raise
    finally:
        con.close()

    print("\nMigration 007 complete.")


if __name__ == "__main__":
    run_migration()
