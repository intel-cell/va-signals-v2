import pytest

import src.db as db
import src.db.core as db_core


def test_schema_path_defaults_to_sqlite(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert db.get_db_backend() == "sqlite"
    assert db.get_schema_path() == db.ROOT / "schema.sql"


@pytest.mark.parametrize(
    "url",
    [
        "postgres://user:pass@localhost:5432/va_signals",
        "postgresql://user:pass@localhost:5432/va_signals",
        "postgresql+psycopg2://user:pass@localhost:5432/va_signals",
    ],
)
def test_schema_path_uses_postgres_when_database_url_set(monkeypatch, url):
    monkeypatch.setenv("DATABASE_URL", url)

    assert db.get_db_backend() == "postgres"
    assert db.get_schema_path() == db.ROOT / "schema.postgres.sql"
    assert db.get_schema_path().exists()


@pytest.mark.parametrize(
    ("raw_url", "expected"),
    [
        (
            "postgresql+psycopg2://user:pass@localhost:5432/va_signals",
            "postgresql://user:pass@localhost:5432/va_signals",
        ),
        (
            "postgresql+psycopg://user:pass@localhost:5432/va_signals?sslmode=require",
            "postgresql://user:pass@localhost:5432/va_signals?sslmode=require",
        ),
        (
            "postgresql://user:pass@localhost:5432/va_signals",
            "postgresql://user:pass@localhost:5432/va_signals",
        ),
        ("", ""),
    ],
)
def test_normalize_db_url_strips_driver_suffix(raw_url, expected):
    assert db._normalize_db_url(raw_url) == expected


def test_count_inserted_rows_postgres_uses_returning(monkeypatch):
    monkeypatch.setattr(db_core, "_is_postgres", lambda: True)

    executed_sql: list[str] = []
    results = [(1,), None, (1,)]

    class DummyCursor:
        def __init__(self, row):
            self._row = row

        def fetchone(self):
            return self._row

    def fake_execute(_con, sql, _params):
        executed_sql.append(sql)
        return DummyCursor(results.pop(0))

    def fake_executemany(*_args, **_kwargs):
        raise AssertionError("executemany should not be used for Postgres counts")

    monkeypatch.setattr(db_core, "execute", fake_execute)
    monkeypatch.setattr(db_core, "executemany", fake_executemany)

    params = [{"doc_id": "a"}, {"doc_id": "b"}, {"doc_id": "c"}]
    sql = "INSERT INTO fr_seen(doc_id) VALUES(:doc_id) ON CONFLICT(doc_id) DO NOTHING"

    inserted = db._count_inserted_rows(object(), sql, params)

    assert inserted == 2
    assert all("RETURNING 1" in statement for statement in executed_sql)


def test_prepare_query_translates_named_params_for_postgres(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@localhost:5432/va_signals")

    sql, params = db._prepare_query(
        "SELECT * FROM fr_seen WHERE doc_id = :doc_id AND source_url = :source_url",
        {"doc_id": "doc-1", "source_url": "https://example.com"},
    )

    assert sql == "SELECT * FROM fr_seen WHERE doc_id = %(doc_id)s AND source_url = %(source_url)s"
    assert params == {"doc_id": "doc-1", "source_url": "https://example.com"}


def test_prepare_query_translates_qmark_params_for_postgres(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/va_signals")

    sql, params = db._prepare_query(
        "SELECT * FROM fr_seen WHERE doc_id = ? AND source_url = ?",
        ("doc-1", "https://example.com"),
    )

    assert sql == "SELECT * FROM fr_seen WHERE doc_id = %s AND source_url = %s"
    assert params == ("doc-1", "https://example.com")


def test_named_params_round_trip_sqlite(tmp_path, monkeypatch):
    test_db = tmp_path / "db-backend.sqlite"
    monkeypatch.setattr(db_core, "DB_PATH", test_db)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    db.init_db()
    con = db.connect()

    db.execute(
        con,
        """INSERT INTO source_runs(
               source_id, started_at, ended_at, status, records_fetched, errors_json
           ) VALUES (
               :source_id, :started_at, :ended_at, :status, :records_fetched, :errors_json
           )""",
        {
            "source_id": "fr_delta",
            "started_at": "2026-01-26T01:00:00Z",
            "ended_at": "2026-01-26T01:05:00Z",
            "status": "SUCCESS",
            "records_fetched": 3,
            "errors_json": "[]",
        },
    )
    con.commit()

    cur = db.execute(
        con,
        "SELECT status, records_fetched FROM source_runs WHERE source_id = :source_id",
        {"source_id": "fr_delta"},
    )
    row = cur.fetchone()
    con.close()

    assert row == ("SUCCESS", 3)
