#!/usr/bin/env python3
"""
Migration: Clean up data quality issues from test contamination.

Removes:
- audit_log entries with ip_address='testclient'
- hearings with far-future placeholder dates (year >= 2099)
- source_runs with stub source_id or started_at values

Run with: python -m migrations.009_cleanup_data_quality
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db import connect, execute


def run_migration(db_path=None):
    """Remove contaminated rows from audit_log, hearings, and source_runs."""
    print("Running migration 009: Clean up data quality issues...")

    con = connect()
    try:
        # 1. Remove test-client audit entries
        cur = execute(
            con,
            "DELETE FROM audit_log WHERE ip_address = 'testclient'",
        )
        audit_count = cur.rowcount
        print(f"  Deleted {audit_count} audit_log rows with ip_address='testclient'")

        # 2. Remove hearings with far-future placeholder dates
        cur = execute(
            con,
            "DELETE FROM hearings WHERE substr(hearing_date, 1, 4) >= '2099'",
        )
        hearing_count = cur.rowcount
        print(f"  Deleted {hearing_count} hearings with placeholder dates (year >= 2099)")

        # 3. Remove source_runs with stub values
        cur = execute(
            con,
            "DELETE FROM source_runs WHERE length(source_id) <= 1 OR length(started_at) <= 1",
        )
        source_run_count = cur.rowcount
        print(f"  Deleted {source_run_count} source_runs with stub source_id or started_at")

        con.commit()

    except Exception as e:
        con.rollback()
        print(f"\nMigration failed: {e}")
        raise
    finally:
        con.close()

    print("\nMigration 009 complete.")


if __name__ == "__main__":
    run_migration()
