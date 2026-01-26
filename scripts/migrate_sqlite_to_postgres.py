import argparse
import os
import sqlite3
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse, urlunparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SQLITE_PATH = ROOT / "data" / "signals.db"
BATCH_SIZE = 500

TABLES_TO_MIGRATE = [
    "source_runs",
    "fr_seen",
    "ecfr_seen",
    "fr_summaries",
    "bills",
    "bill_actions",
    "hearings",
    "hearing_updates",
    "om_events",
    "om_related_coverage",
    "om_baselines",
    "om_rejected",
    "om_escalation_signals",
    "om_digests",
    "state_sources",
    "state_signals",
    "state_classifications",
    "state_notifications",
    "state_runs",
    "state_source_health",
    "signal_suppression",
    "signal_audit_log",
    "ad_members",
    "ad_utterances",
    "ad_embeddings",
    "ad_baselines",
    "ad_deviation_events",
]

FK_RELATIONSHIPS = [
    ("fr_summaries", "doc_id", "fr_seen", "doc_id"),
    ("ad_utterances", "member_id", "ad_members", "member_id"),
    ("ad_embeddings", "utterance_id", "ad_utterances", "utterance_id"),
    ("ad_baselines", "member_id", "ad_members", "member_id"),
    ("ad_deviation_events", "member_id", "ad_members", "member_id"),
    ("ad_deviation_events", "utterance_id", "ad_utterances", "utterance_id"),
    ("ad_deviation_events", "baseline_id", "ad_baselines", "id"),
    ("bill_actions", "bill_id", "bills", "bill_id"),
    ("hearing_updates", "event_id", "hearings", "event_id"),
    ("om_related_coverage", "event_id", "om_events", "event_id"),
    ("state_signals", "source_id", "state_sources", "source_id"),
    ("state_classifications", "signal_id", "state_signals", "signal_id"),
    ("state_notifications", "signal_id", "state_signals", "signal_id"),
    ("state_source_health", "source_id", "state_sources", "source_id"),
]


def _normalize_db_url(db_url: str) -> str:
    if not db_url:
        return db_url
    parsed = urlparse(db_url)
    scheme = parsed.scheme
    if "+" not in scheme:
        return db_url
    base_scheme = scheme.split("+", 1)[0]
    if not base_scheme or base_scheme == scheme:
        return db_url
    return urlunparse(parsed._replace(scheme=base_scheme))


def _resolve_sqlite_path(cli_path: str | None) -> Path:
    if cli_path:
        return Path(cli_path).expanduser()
    env_path = os.environ.get("DB_PATH", "").strip()
    if env_path:
        return Path(env_path).expanduser()
    return DEFAULT_SQLITE_PATH


def _sqlite_table_exists(con: sqlite3.Connection, table: str) -> bool:
    cur = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    return cur.fetchone() is not None


def _sqlite_table_columns(con: sqlite3.Connection, table: str) -> list[str]:
    cur = con.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cur.fetchall()]


def _sqlite_table_count(con: sqlite3.Connection, table: str) -> int:
    cur = con.execute(f"SELECT COUNT(*) FROM {table}")
    row = cur.fetchone()
    return int(row[0]) if row else 0


def _sqlite_table_has_column(con: sqlite3.Connection, table: str, column: str) -> bool:
    return column in _sqlite_table_columns(con, table)


def _iter_sqlite_rows(
    con: sqlite3.Connection,
    table: str,
    batch_size: int = BATCH_SIZE,
) -> Iterable[list[tuple]]:
    cur = con.execute(f"SELECT * FROM {table}")
    while True:
        rows = cur.fetchmany(batch_size)
        if not rows:
            break
        yield rows


def _print_counts(con: sqlite3.Connection) -> None:
    for table in TABLES_TO_MIGRATE:
        if not _sqlite_table_exists(con, table):
            print(f"{table}: 0 (missing)")
            continue
        count = _sqlite_table_count(con, table)
        print(f"{table}: {count}")


def _connect_postgres():
    db_url = os.environ.get("DATABASE_URL", "").strip()
    if not db_url:
        raise RuntimeError("DATABASE_URL must be set for Postgres migration.")
    db_url = _normalize_db_url(db_url)
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("psycopg is required for Postgres migration.") from exc
    return psycopg.connect(db_url)


def _build_insert_statement(table: str, columns: list[str]):
    from psycopg import sql

    return sql.SQL(
        "INSERT INTO {table} ({cols}) VALUES ({values}) ON CONFLICT DO NOTHING"
    ).format(
        table=sql.Identifier(table),
        cols=sql.SQL(", ").join(sql.Identifier(col) for col in columns),
        values=sql.SQL(", ").join(sql.Placeholder() for _ in columns),
    )


def _check_sqlite_foreign_keys(con: sqlite3.Connection) -> None:
    orphans = []
    for child_table, child_col, parent_table, parent_col in FK_RELATIONSHIPS:
        if not _sqlite_table_exists(con, child_table):
            continue
        if not _sqlite_table_has_column(con, child_table, child_col):
            continue
        if not _sqlite_table_exists(con, parent_table):
            cur = con.execute(
                f"SELECT COUNT(*) FROM {child_table} WHERE {child_col} IS NOT NULL"
            )
            count = int(cur.fetchone()[0])
        else:
            if not _sqlite_table_has_column(con, parent_table, parent_col):
                continue
            cur = con.execute(
                "SELECT COUNT(*) "
                f"FROM {child_table} c "
                f"LEFT JOIN {parent_table} p "
                f"ON c.{child_col} = p.{parent_col} "
                f"WHERE c.{child_col} IS NOT NULL "
                f"AND p.{parent_col} IS NULL"
            )
            count = int(cur.fetchone()[0])
        if count:
            orphans.append((child_table, child_col, parent_table, parent_col, count))

    if orphans:
        lines = [
            "SQLite foreign key check failed; fix or re-run with --skip-fk-checks."
        ]
        for child_table, child_col, parent_table, parent_col, count in orphans:
            lines.append(
                f"- {child_table}.{child_col} -> {parent_table}.{parent_col}: "
                f"{count} orphan(s)"
            )
        raise RuntimeError("\n".join(lines))


def _reset_postgres_sequences(pg_con, tables: Iterable[str]) -> None:
    with pg_con.cursor() as cur:
        for table in tables:
            cur.execute("SELECT pg_get_serial_sequence(%s, %s)", (table, "id"))
            row = cur.fetchone()
            sequence = row[0] if row else None
            if not sequence:
                continue
            cur.execute(
                f"SELECT setval(%s::regclass, COALESCE(MAX(id), 1), "
                f"MAX(id) IS NOT NULL) FROM {table}",
                (sequence,),
            )
    pg_con.commit()


def migrate(sqlite_path: Path, dry_run: bool, skip_fk_checks: bool = False) -> None:
    if not sqlite_path.exists():
        raise FileNotFoundError(f"SQLite DB not found: {sqlite_path}")
    sqlite_con = sqlite3.connect(sqlite_path)
    try:
        print(f"SQLite: {sqlite_path}")
        if dry_run:
            print("Dry run: no Postgres writes")
            _print_counts(sqlite_con)
            return
        if not skip_fk_checks:
            _check_sqlite_foreign_keys(sqlite_con)

        pg_con = _connect_postgres()
        try:
            _print_counts(sqlite_con)
            tables_with_ids: list[str] = []
            for table in TABLES_TO_MIGRATE:
                if not _sqlite_table_exists(sqlite_con, table):
                    continue
                columns = _sqlite_table_columns(sqlite_con, table)
                if not columns:
                    continue
                if "id" in columns:
                    tables_with_ids.append(table)
                insert_sql = _build_insert_statement(table, columns)
                with pg_con.cursor() as cur:
                    for batch in _iter_sqlite_rows(sqlite_con, table):
                        cur.executemany(insert_sql, batch)
                pg_con.commit()
            if tables_with_ids:
                _reset_postgres_sequences(pg_con, tables_with_ids)
        finally:
            pg_con.close()
    finally:
        sqlite_con.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate VA Signals SQLite data to Postgres."
    )
    parser.add_argument(
        "--sqlite-path",
        help="Path to SQLite DB (defaults to DB_PATH env var or data/signals.db).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print counts only; do not connect to Postgres.",
    )
    parser.add_argument(
        "--skip-fk-checks",
        action="store_true",
        help="Skip SQLite foreign key orphan checks before migrating.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    sqlite_path = _resolve_sqlite_path(args.sqlite_path)
    migrate(sqlite_path, args.dry_run, args.skip_fk_checks)


if __name__ == "__main__":
    main()
