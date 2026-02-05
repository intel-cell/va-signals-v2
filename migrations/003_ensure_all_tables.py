#!/usr/bin/env python3
"""Ensure all required tables exist in production database."""
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Import db module for connection
from src.db import connect, execute

# Tables that might be missing
ENSURE_TABLES = [
    # Audit log
    """
    CREATE TABLE IF NOT EXISTS audit_log (
        log_id TEXT PRIMARY KEY,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        user_id TEXT,
        user_email TEXT,
        action TEXT NOT NULL,
        resource TEXT,
        resource_id TEXT,
        request_method TEXT,
        request_path TEXT,
        request_body TEXT,
        response_status INTEGER,
        ip_address TEXT,
        user_agent TEXT,
        duration_ms INTEGER,
        success BOOLEAN
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_audit_log_user ON audit_log(user_email, timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action, timestamp)",
]


def main():
    logger.info("Ensuring all required tables exist...")
    con = connect()
    
    for i, stmt in enumerate(ENSURE_TABLES):
        try:
            execute(con, stmt, {})
            logger.info(f"Statement {i+1}/{len(ENSURE_TABLES)} executed")
        except Exception as e:
            logger.warning(f"Statement {i+1} warning: {e}")
    
    con.commit()
    con.close()
    logger.info("Migration complete!")


if __name__ == "__main__":
    main()
