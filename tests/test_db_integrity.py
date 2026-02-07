"""Tests for LOE2 data integrity: post-write verification, partial failure
handling, router connection safety, and config schema validation."""

from unittest.mock import MagicMock, patch

import pytest
import yaml

import src.db as db
from src.db.core import executemany
from src.db.helpers import insert_source_run
from src.resilience.staleness_monitor import load_expectations

# ── helpers ──────────────────────────────────────────────────────


def _make_run(**overrides):
    base = {
        "source_id": "test_source",
        "started_at": "2024-01-01T00:00:00Z",
        "ended_at": "2024-01-01T01:00:00Z",
        "status": "SUCCESS",
        "records_fetched": 10,
        "errors": [],
    }
    base.update(overrides)
    return base


# ── Task #5: Post-write verification ────────────────────────────


class TestInsertSourceRunVerification:
    def test_returns_row_id_on_success(self):
        row_id = insert_source_run(_make_run())
        assert isinstance(row_id, int)
        assert row_id > 0

    def test_returns_none_for_invalid_source_id(self):
        result = insert_source_run(_make_run(source_id=""))
        assert result is None

    def test_returns_none_for_invalid_started_at(self):
        result = insert_source_run(_make_run(started_at=""))
        assert result is None

    def test_row_exists_after_insert(self):
        row_id = insert_source_run(_make_run(source_id="verify_test"))
        assert row_id is not None
        con = db.connect()
        cur = db.execute(
            con,
            "SELECT source_id FROM source_runs WHERE id = :id",
            {"id": row_id},
        )
        row = cur.fetchone()
        con.close()
        assert row is not None
        assert row[0] == "verify_test"


# ── Task #6: Partial failure handling ────────────────────────────


class TestExecutemanyPartialFailure:
    def test_normal_batch_succeeds(self):
        con = db.connect()
        cur = executemany(
            con,
            "INSERT INTO fr_seen(doc_id, published_date, first_seen_at, source_url) VALUES(:doc_id, :published_date, :first_seen_at, :source_url)",
            [
                {
                    "doc_id": "BATCH-A",
                    "published_date": "2024-01-01",
                    "first_seen_at": "2024-01-01T00:00:00Z",
                    "source_url": "u1",
                },
                {
                    "doc_id": "BATCH-B",
                    "published_date": "2024-01-01",
                    "first_seen_at": "2024-01-01T00:00:00Z",
                    "source_url": "u2",
                },
            ],
        )
        con.commit()
        con.close()
        # Both rows should exist
        con = db.connect()
        cur = db.execute(con, "SELECT COUNT(*) FROM fr_seen WHERE doc_id IN ('BATCH-A', 'BATCH-B')")
        assert cur.fetchone()[0] == 2
        con.close()

    def test_fallback_on_batch_failure(self):
        """When executemany fails, it should fall back to row-by-row."""
        mock_cursor = MagicMock()
        # executemany raises, individual execute succeeds
        mock_cursor.executemany.side_effect = Exception("batch error")
        mock_cursor.execute.return_value = None

        mock_con = MagicMock()
        mock_con.cursor.return_value = mock_cursor

        params = [
            {"doc_id": "F1", "date": "2024-01-01"},
            {"doc_id": "F2", "date": "2024-01-02"},
        ]

        cur = executemany(mock_con, "INSERT INTO t(doc_id, date) VALUES(:doc_id, :date)", params)

        # Should have called execute for each row after executemany failed
        assert mock_cursor.execute.call_count == 2
        assert cur.rowcount == 2

    def test_fallback_counts_partial_success(self):
        """When some rows fail in fallback, rowcount reflects only successes."""
        mock_cursor = MagicMock()
        mock_cursor.executemany.side_effect = Exception("batch error")
        # First row succeeds, second fails
        mock_cursor.execute.side_effect = [None, Exception("row error")]

        mock_con = MagicMock()
        mock_con.cursor.return_value = mock_cursor

        params = [
            {"doc_id": "G1"},
            {"doc_id": "G2"},
        ]

        cur = executemany(mock_con, "INSERT INTO t(doc_id) VALUES(:doc_id)", params)
        assert cur.rowcount == 1

    def test_empty_params_returns_cursor(self):
        con = db.connect()
        cur = executemany(con, "INSERT INTO fr_seen(doc_id) VALUES(?)", [])
        con.close()
        assert cur is not None


# ── Task #7: Router connection safety ────────────────────────────


class TestRouterConnectionSafety:
    def test_legislative_get_bills_closes_on_error(self):
        """Verify get_bills closes DB connection even when query raises."""
        mock_con = MagicMock()
        mock_con.cursor.return_value.execute.side_effect = Exception("DB error")

        with patch("src.routers.legislative.connect", return_value=mock_con):
            with patch("src.routers.legislative.table_exists", return_value=True):
                with pytest.raises(Exception, match="DB error"):
                    from src.routers.legislative import get_bills

                    get_bills(limit=10, congress=None, _=None)

        mock_con.close.assert_called_once()

    def test_pipeline_get_runs_closes_on_error(self):
        """Verify get_runs closes DB connection even when query raises."""
        mock_con = MagicMock()
        mock_con.cursor.return_value.execute.side_effect = Exception("DB error")

        with patch("src.routers.pipeline.connect", return_value=mock_con):
            with pytest.raises(Exception, match="DB error"):
                from src.routers.pipeline import get_runs

                get_runs(source_id=None, status=None, limit=10, _=None)

        mock_con.close.assert_called_once()

    def test_health_get_health_closes_on_error(self):
        """Verify get_health closes DB connection even when query raises."""
        mock_con = MagicMock()
        mock_con.cursor.return_value.execute.side_effect = Exception("DB error")

        with patch("src.routers.health.connect", return_value=mock_con):
            with pytest.raises(Exception, match="DB error"):
                from src.routers.health import get_health

                get_health(_=None)

        mock_con.close.assert_called_once()

    def test_health_get_deadman_closes_on_error(self):
        """Verify get_deadman_switch closes DB connection even when query raises."""
        mock_con = MagicMock()
        mock_con.cursor.return_value.execute.side_effect = Exception("DB error")

        with patch("src.routers.health.connect", return_value=mock_con):
            with pytest.raises(Exception, match="DB error"):
                from src.routers.health import get_deadman_switch

                get_deadman_switch(_=None)

        mock_con.close.assert_called_once()


# ── Task #8: Config schema validation ───────────────────────────


class TestConfigSchemaValidation:
    def test_valid_config_loads(self):
        """The real source_expectations.yaml should validate."""
        expectations = load_expectations()
        assert len(expectations) > 0

    def test_invalid_frequency_rejected(self, tmp_path):
        """An invalid frequency value should be rejected by schema."""
        bad_config = {
            "sources": {
                "test_source": {
                    "frequency": "hourly",  # invalid, must be daily or weekly
                    "tolerance_hours": 6,
                    "alert_after_hours": 24,
                    "is_critical": True,
                }
            }
        }
        config_file = tmp_path / "bad_expectations.yaml"
        config_file.write_text(yaml.dump(bad_config))

        from jsonschema import ValidationError

        with pytest.raises(ValidationError):
            load_expectations(config_path=config_file)

    def test_missing_required_field_rejected(self, tmp_path):
        """Missing required fields should be rejected."""
        bad_config = {
            "sources": {
                "test_source": {
                    "frequency": "daily",
                    # missing tolerance_hours, alert_after_hours, is_critical
                }
            }
        }
        config_file = tmp_path / "incomplete.yaml"
        config_file.write_text(yaml.dump(bad_config))

        from jsonschema import ValidationError

        with pytest.raises(ValidationError):
            load_expectations(config_path=config_file)

    def test_negative_tolerance_rejected(self, tmp_path):
        """Negative tolerance_hours should fail validation."""
        bad_config = {
            "sources": {
                "test_source": {
                    "frequency": "daily",
                    "tolerance_hours": -1,
                    "alert_after_hours": 24,
                    "is_critical": False,
                }
            }
        }
        config_file = tmp_path / "negative.yaml"
        config_file.write_text(yaml.dump(bad_config))

        from jsonschema import ValidationError

        with pytest.raises(ValidationError):
            load_expectations(config_path=config_file)

    def test_missing_config_returns_empty(self, tmp_path):
        """Non-existent config should return empty list, not raise."""
        result = load_expectations(config_path=tmp_path / "nonexistent.yaml")
        assert result == []

    def test_extra_fields_rejected(self, tmp_path):
        """Extra unknown fields should be rejected by schema."""
        bad_config = {
            "sources": {
                "test_source": {
                    "frequency": "daily",
                    "tolerance_hours": 6,
                    "alert_after_hours": 24,
                    "is_critical": True,
                    "unknown_field": "bad",
                }
            }
        }
        config_file = tmp_path / "extra.yaml"
        config_file.write_text(yaml.dump(bad_config))

        from jsonschema import ValidationError

        with pytest.raises(ValidationError):
            load_expectations(config_path=config_file)
