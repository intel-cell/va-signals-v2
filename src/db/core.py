"""Core database infrastructure — connect, execute, schema helpers."""

import logging
import os
import re
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "signals.db"
SCHEMA_PATH = ROOT / "schema.sql"
SCHEMA_POSTGRES_PATH = ROOT / "schema.postgres.sql"

_NAMED_PARAM_RE = re.compile(r"(?<!:):([a-zA-Z_][a-zA-Z0-9_]*)")


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


def _is_postgres() -> bool:
    return get_db_backend() == "postgres"


def _prepare_query(sql: str, params: Mapping[str, Any] | Sequence[Any] | None):
    """
    Normalize parameter style for the active backend.
    - SQLite: accepts :name or ? placeholders as-is.
    - Postgres (psycopg): translate :name -> %(name)s and ? -> %s.
    """
    if params is None or not _is_postgres():
        return sql, params

    if isinstance(params, Mapping):
        return _NAMED_PARAM_RE.sub(r"%(\1)s", sql), params

    return sql.replace("?", "%s"), params


def execute(con, sql: str, params: Mapping[str, Any] | Sequence[Any] | None = None):
    cur = con.cursor()
    sql, params = _prepare_query(sql, params)
    if params is None:
        cur.execute(sql)
    else:
        cur.execute(sql, params)
    return cur


def executemany(
    con,
    sql: str,
    params_seq: Iterable[Mapping[str, Any]] | Iterable[Sequence[Any]],
):
    cur = con.cursor()
    params_list = list(params_seq)
    if not params_list:
        return cur
    sql, _ = _prepare_query(sql, params_list[0])
    try:
        cur.executemany(sql, params_list)
    except Exception:
        logger.warning(
            "executemany batch failed, falling back to row-by-row execution (%d rows)",
            len(params_list),
        )
        success_count = 0
        for i, params in enumerate(params_list):
            try:
                cur.execute(sql, params)
                success_count += 1
            except Exception:
                logger.warning(
                    "Row %d failed in row-by-row fallback: params=%r",
                    i,
                    dict(params.items() if isinstance(params, Mapping) else enumerate(params)),
                )
        cur.rowcount = success_count
    return cur


def _count_inserted_rows(
    con,
    sql: str,
    params_seq: Iterable[Mapping[str, Any]] | Iterable[Sequence[Any]],
) -> int:
    params_list = list(params_seq)
    if not params_list:
        return 0
    if _is_postgres():
        returning_sql = sql
        if "returning" not in sql.lower():
            returning_sql = f"{sql} RETURNING 1"
        inserted = 0
        for params in params_list:
            cur = execute(con, returning_sql, params)
            if cur.fetchone():
                inserted += 1
        return inserted
    cur = executemany(con, sql, params_list)
    return cur.rowcount


def table_exists(con, table_name: str) -> bool:
    if _is_postgres():
        cur = execute(con, "SELECT to_regclass(:table_name)", {"table_name": table_name})
        row = cur.fetchone()
        return row is not None and row[0] is not None
    cur = execute(
        con,
        "SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name",
        {"table_name": table_name},
    )
    return cur.fetchone() is not None


def insert_returning_id(con, sql: str, params: Mapping[str, Any], id_column: str = "id"):
    if _is_postgres():
        cur = execute(con, f"{sql} RETURNING {id_column}", params)
        row = cur.fetchone()
        return row[0] if row else None
    cur = execute(con, sql, params)
    return cur.lastrowid


def get_db_backend() -> str:
    db_url = os.environ.get("DATABASE_URL", "").strip()
    if not db_url:
        return "sqlite"
    scheme = urlparse(db_url).scheme.lower()
    if scheme.startswith("postgres"):
        return "postgres"
    return "sqlite"


def get_schema_path() -> Path:
    if get_db_backend() == "postgres":
        return SCHEMA_POSTGRES_PATH
    return SCHEMA_PATH


def connect():
    if _is_postgres():
        db_url = os.environ.get("DATABASE_URL", "").strip()
        if not db_url:
            raise RuntimeError("DATABASE_URL must be set for Postgres backend.")
        db_url = _normalize_db_url(db_url)
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("psycopg is required for Postgres support.") from exc
        return psycopg.connect(db_url)

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.execute("PRAGMA journal_mode=WAL")
    return con


def init_db():
    con = connect()
    schema_sql = get_schema_path().read_text(encoding="utf-8")
    if _is_postgres():
        statements = [s.strip() for s in schema_sql.split(";") if s.strip()]
        cur = con.cursor()
        for statement in statements:
            cur.execute(statement)
        con.commit()
        con.close()
        return
    con.executescript(schema_sql)
    con.commit()
    con.close()


def assert_tables_exist():
    con = connect()
    required = {"source_runs", "fr_seen"}
    missing = {name for name in required if not table_exists(con, name)}
    con.close()
    if missing:
        raise RuntimeError(f"DB_SCHEMA_MISSING_TABLES: {sorted(missing)}")
