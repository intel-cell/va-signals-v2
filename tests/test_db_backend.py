import pytest

import src.db as db


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
    monkeypatch.setattr(db, "DB_PATH", test_db)
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
