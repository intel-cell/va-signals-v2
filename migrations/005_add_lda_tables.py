#!/usr/bin/env python3
"""
Migration: Add LDA.gov Lobbying Disclosure tables.

Creates tables for:
- lda_filings: Lobbying disclosure filings (registrations, quarterly, amendments)
- lda_alerts: Alerts generated from high-relevance filings

Run with: python -m migrations.005_add_lda_tables
"""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db import connect, execute

LDA_TABLES = [
    """
    CREATE TABLE IF NOT EXISTS lda_filings (
        filing_uuid TEXT PRIMARY KEY,
        filing_type TEXT NOT NULL,
        filing_year INTEGER,
        filing_period TEXT,
        dt_posted TEXT NOT NULL,
        registrant_name TEXT NOT NULL,
        registrant_id TEXT,
        client_name TEXT NOT NULL,
        client_id TEXT,
        income_amount REAL,
        expense_amount REAL,
        lobbying_issues_json TEXT,
        specific_issues_text TEXT,
        govt_entities_json TEXT,
        lobbyists_json TEXT,
        foreign_entity_listed INTEGER DEFAULT 0,
        foreign_entities_json TEXT,
        covered_positions_json TEXT,
        source_url TEXT NOT NULL,
        first_seen_at TEXT NOT NULL,
        updated_at TEXT,
        va_relevance_score TEXT DEFAULT 'LOW',
        va_relevance_reason TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS lda_alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filing_uuid TEXT NOT NULL,
        alert_type TEXT NOT NULL,
        severity TEXT NOT NULL,
        summary TEXT NOT NULL,
        details_json TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        acknowledged INTEGER DEFAULT 0,
        FOREIGN KEY (filing_uuid) REFERENCES lda_filings(filing_uuid)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_lda_filings_posted ON lda_filings(dt_posted)",
    "CREATE INDEX IF NOT EXISTS idx_lda_filings_type ON lda_filings(filing_type)",
    "CREATE INDEX IF NOT EXISTS idx_lda_filings_relevance ON lda_filings(va_relevance_score)",
    "CREATE INDEX IF NOT EXISTS idx_lda_alerts_severity ON lda_alerts(severity)",
    "CREATE INDEX IF NOT EXISTS idx_lda_alerts_filing ON lda_alerts(filing_uuid)",
]


def run_migration():
    """Run the LDA tables migration."""
    print("Running LDA tables migration...")

    con = connect()
    try:
        for sql in LDA_TABLES:
            try:
                execute(con, sql)
                print(f"  ✓ Executed: {sql.strip()[:60]}...")
            except Exception as e:
                print(f"  ⚠ Warning: {e}")

        con.commit()
        print("\n✅ LDA tables migration completed successfully!")

    except Exception as e:
        con.rollback()
        print(f"\n❌ Migration failed: {e}")
        raise
    finally:
        con.close()


if __name__ == "__main__":
    run_migration()
