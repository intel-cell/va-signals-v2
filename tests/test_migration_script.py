import importlib.util
import sqlite3
from pathlib import Path


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
