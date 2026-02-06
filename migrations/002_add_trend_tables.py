#!/usr/bin/env python3
"""One-time migration to add trend tables to PostgreSQL."""
import logging
from src.db import connect, execute

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Individual SQL statements (can't run multiple in one execute with SQLite-style)
MIGRATION_STATEMENTS = [
    # Trend daily signals
    """
    CREATE TABLE IF NOT EXISTS trend_daily_signals (
        id SERIAL PRIMARY KEY,
        date TEXT NOT NULL,
        trigger_id TEXT NOT NULL,
        signal_count INTEGER NOT NULL DEFAULT 0,
        suppressed_count INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(date, trigger_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_trend_signals_date ON trend_daily_signals(date)",
    "CREATE INDEX IF NOT EXISTS idx_trend_signals_trigger ON trend_daily_signals(trigger_id)",

    # Trend daily source health
    """
    CREATE TABLE IF NOT EXISTS trend_daily_source_health (
        id SERIAL PRIMARY KEY,
        date TEXT NOT NULL,
        source_id TEXT NOT NULL,
        run_count INTEGER NOT NULL DEFAULT 0,
        success_count INTEGER NOT NULL DEFAULT 0,
        error_count INTEGER NOT NULL DEFAULT 0,
        no_data_count INTEGER NOT NULL DEFAULT 0,
        total_docs INTEGER NOT NULL DEFAULT 0,
        success_rate REAL NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(date, source_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_trend_source_date ON trend_daily_source_health(date)",
    "CREATE INDEX IF NOT EXISTS idx_trend_source_id ON trend_daily_source_health(source_id)",

    # Trend weekly oversight
    """
    CREATE TABLE IF NOT EXISTS trend_weekly_oversight (
        id SERIAL PRIMARY KEY,
        week_start TEXT NOT NULL UNIQUE,
        week_end TEXT NOT NULL,
        total_events INTEGER NOT NULL DEFAULT 0,
        escalations INTEGER NOT NULL DEFAULT 0,
        deviations INTEGER NOT NULL DEFAULT 0,
        by_source_json TEXT,
        by_theme_json TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_trend_oversight_week ON trend_weekly_oversight(week_start)",

    # Trend daily battlefield
    """
    CREATE TABLE IF NOT EXISTS trend_daily_battlefield (
        id SERIAL PRIMARY KEY,
        date TEXT NOT NULL UNIQUE,
        total_vehicles INTEGER NOT NULL DEFAULT 0,
        active_vehicles INTEGER NOT NULL DEFAULT 0,
        critical_gates INTEGER NOT NULL DEFAULT 0,
        alerts_count INTEGER NOT NULL DEFAULT 0,
        by_type_json TEXT,
        by_posture_json TEXT,
        by_stage_json TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_trend_battlefield_date ON trend_daily_battlefield(date)",
]

# FR columns - handle separately as ALTER TABLE
FR_COLUMN_STATEMENTS = [
    "ALTER TABLE fr_seen ADD COLUMN IF NOT EXISTS comments_close_date TEXT",
    "ALTER TABLE fr_seen ADD COLUMN IF NOT EXISTS effective_date TEXT",
    "ALTER TABLE fr_seen ADD COLUMN IF NOT EXISTS document_type TEXT",
    "ALTER TABLE fr_seen ADD COLUMN IF NOT EXISTS title TEXT",
]


def main():
    logger.info("Starting migration: add trend tables")

    con = connect()

    # Run trend table migrations
    for i, stmt in enumerate(MIGRATION_STATEMENTS):
        try:
            execute(con, stmt, {})
            logger.info(f"Statement {i+1}/{len(MIGRATION_STATEMENTS)} executed")
        except Exception as e:
            logger.warning(f"Statement {i+1} warning: {e}")

    # Run FR column migrations
    for stmt in FR_COLUMN_STATEMENTS:
        try:
            execute(con, stmt, {})
            logger.info(f"FR column migration executed: {stmt[:50]}...")
        except Exception as e:
            logger.warning(f"FR column warning (may already exist): {e}")

    con.commit()

    # Verify tables exist
    try:
        cur = execute(con, """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name LIKE 'trend_%'
        """, {})
        tables = [row[0] for row in cur.fetchall()]
        logger.info(f"Trend tables verified: {tables}")
    except Exception as e:
        # SQLite fallback
        cur = execute(con, "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'trend_%'", {})
        tables = [row[0] for row in cur.fetchall()]
        logger.info(f"Trend tables verified (SQLite): {tables}")

    con.close()
    logger.info("Migration complete!")


if __name__ == "__main__":
    main()
