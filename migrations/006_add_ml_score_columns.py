#!/usr/bin/env python3
"""
Migration: Add ML scoring columns to om_events table.

Adds ml_score (REAL) and ml_risk_level (TEXT) for storing
predictive scoring results on oversight monitor events.

Run with: python -m migrations.006_add_ml_score_columns
"""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db import connect, execute

ALTER_STATEMENTS = [
    "ALTER TABLE om_events ADD COLUMN ml_score REAL",
    "ALTER TABLE om_events ADD COLUMN ml_risk_level TEXT",
]


def run_migration():
    """Add ml_score and ml_risk_level columns to om_events."""
    print("Running migration 006: Add ML score columns to om_events...")

    con = connect()
    try:
        for sql in ALTER_STATEMENTS:
            try:
                execute(con, sql)
                print(f"  OK: {sql}")
            except Exception as e:
                print(f"  Skipped (already exists): {e}")

        con.commit()
        print("\nMigration 006: Added ml_score and ml_risk_level to om_events")

    except Exception as e:
        con.rollback()
        print(f"\nMigration failed: {e}")
        raise
    finally:
        con.close()


if __name__ == "__main__":
    run_migration()
