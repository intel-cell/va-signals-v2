import importlib.util
import sqlite3
from pathlib import Path

import pytest


def _load_migration_module():
    root = Path(__file__).resolve().parents[1]
    script_path = root / "scripts" / "migrate_sqlite_to_postgres.py"
    assert script_path.exists(), "migration script is missing"
    spec = importlib.util.spec_from_file_location("migrate_sqlite_to_postgres", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_migration_dry_run_outputs_counts(tmp_path, capsys):
    db_path = tmp_path / "signals.db"
    con = sqlite3.connect(db_path)
    con.execute("CREATE TABLE source_runs (id INTEGER)")
    con.execute("INSERT INTO source_runs (id) VALUES (1)")
    con.commit()
    con.close()

    module = _load_migration_module()
    module.main(["--sqlite-path", str(db_path), "--dry-run"])

    out = capsys.readouterr().out
    assert "source_runs: 1" in out


class _StubCursor:
    def __init__(self, queries, sequences):
        self._queries = queries
        self._sequences = sequences
        self._last_table = None

    def execute(self, query, params=None):
        self._queries.append((query, params))
        if "pg_get_serial_sequence" in str(query):
            self._last_table = params[0] if params else None
        else:
            self._last_table = None

    def fetchone(self):
        if self._last_table is None:
            return None
        sequence = self._sequences.get(self._last_table)
        return (sequence,) if sequence else (None,)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _StubConnection:
    def __init__(self, sequences):
        self.sequences = sequences
        self.queries = []
        self.commit_calls = 0

    def cursor(self):
        return _StubCursor(self.queries, self.sequences)

    def commit(self):
        self.commit_calls += 1


def test_sequence_reset_issues_setval():
    module = _load_migration_module()
    pg_con = _StubConnection({"bill_actions": "public.bill_actions_id_seq"})

    module._reset_postgres_sequences(pg_con, ["bill_actions"])

    executed = " ".join(str(query) for query, _ in pg_con.queries)
    assert "pg_get_serial_sequence" in executed
    assert "setval" in executed
    assert pg_con.commit_calls == 1


def test_fk_check_raises_on_orphan(tmp_path):
    db_path = tmp_path / "signals.db"
    con = sqlite3.connect(db_path)
    try:
        con.execute("CREATE TABLE fr_seen (doc_id TEXT)")
        con.execute("CREATE TABLE fr_summaries (doc_id TEXT)")
        con.execute("INSERT INTO fr_summaries (doc_id) VALUES ('missing')")
        con.commit()
        module = _load_migration_module()
        with pytest.raises(RuntimeError) as excinfo:
            module._check_sqlite_foreign_keys(con)
        assert "fr_summaries.doc_id -> fr_seen.doc_id" in str(excinfo.value)
    finally:
        con.close()
