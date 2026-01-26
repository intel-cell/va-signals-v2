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
    ],
)
def test_schema_path_uses_postgres_when_database_url_set(monkeypatch, url):
    monkeypatch.setenv("DATABASE_URL", url)

    assert db.get_db_backend() == "postgres"
    assert db.get_schema_path() == db.ROOT / "schema.postgres.sql"
    assert db.get_schema_path().exists()
