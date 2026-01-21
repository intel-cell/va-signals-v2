import sys
import tempfile
from pathlib import Path

import pytest

# Ensure project root is on sys.path so `import src` works when tests run from any CWD/import mode.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT_STR = str(PROJECT_ROOT)
if PROJECT_ROOT_STR not in sys.path:
    sys.path.insert(0, PROJECT_ROOT_STR)


@pytest.fixture(autouse=True)
def use_test_db(tmp_path, monkeypatch):
    """Use a temporary database for each test."""
    import src.db as db_module

    test_db = tmp_path / "test_signals.db"
    monkeypatch.setattr(db_module, "DB_PATH", test_db)

    # Initialize the schema
    db_module.init_db()

    yield

    # Cleanup - close any lingering connections
    if test_db.exists():
        test_db.unlink()
