"""
Migration 001: Add date columns to fr_seen table

Adds:
- comments_close_date TEXT
- effective_date TEXT
- document_type TEXT
- title TEXT

Run with: python -m migrations.001_add_fr_date_columns
"""

import sqlite3
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import connect, execute


def get_existing_columns(con, table_name: str) -> set[str]:
    """Get existing column names for a table."""
    cursor = con.execute(f"PRAGMA table_info({table_name})")
    return {row[1] for row in cursor.fetchall()}


def migrate():
    """Add new columns to fr_seen if they don't exist."""
    con = connect()

    existing_cols = get_existing_columns(con, "fr_seen")

    columns_to_add = [
        ("comments_close_date", "TEXT"),
        ("effective_date", "TEXT"),
        ("document_type", "TEXT"),
        ("title", "TEXT"),
    ]

    added = []
    for col_name, col_type in columns_to_add:
        if col_name not in existing_cols:
            sql = f"ALTER TABLE fr_seen ADD COLUMN {col_name} {col_type}"
            print(f"Adding column: {col_name}")
            con.execute(sql)
            added.append(col_name)

    con.commit()
    con.close()

    if added:
        print(f"Migration complete. Added columns: {', '.join(added)}")
    else:
        print("Migration skipped. All columns already exist.")

    return added


if __name__ == "__main__":
    migrate()
