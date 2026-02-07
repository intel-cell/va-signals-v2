"""Tests for src/run_hearings.py — CLI runner for VA Hearings sync."""

import json
from unittest.mock import MagicMock, patch

import pytest

from src import run_hearings
import src.db as db


# ── helpers ──────────────────────────────────────────────────────

def _insert_test_hearing(**overrides):
    base = {
        "event_id": "EVT-100", "congress": 119, "chamber": "House",
        "committee_code": "hsvr00", "committee_name": "Veterans Affairs",
        "hearing_date": "2035-06-15", "hearing_time": "10:00",
        "title": "VA Budget Hearing", "meeting_type": "hearing",
        "status": "scheduled", "location": "Room 334",
        "url": "https://congress.gov/h/1", "witnesses_json": "[]",
    }
    base.update(overrides)
    db.upsert_hearing(base)


def _make_schema_file(tmp_path):
    schemas_dir = tmp_path / "schemas"
    schemas_dir.mkdir()
    (schemas_dir / "source_run.schema.json").write_text(json.dumps({
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["source_id", "started_at", "ended_at", "status", "records_fetched", "errors"],
        "properties": {
            "source_id": {"type": "string"},
            "started_at": {"type": "string"},
            "ended_at": {"type": "string"},
            "status": {"type": "string", "enum": ["SUCCESS", "NO_DATA", "ERROR"]},
            "records_fetched": {"type": "integer", "minimum": 0},
            "errors": {"type": "array", "items": {"type": "string"}},
        },
    }))


# ── Argument parsing ─────────────────────────────────────────────

class TestMainArgParsing:
    @patch.object(run_hearings, "run_hearings_sync")
    @patch.object(run_hearings, "print_summary")
    @patch.object(run_hearings, "init_db")
    def test_default_runs_sync(self, mock_init, mock_summary, mock_sync):
        with patch("sys.argv", ["prog"]):
            run_hearings.main()
        mock_sync.assert_called_once_with(full=False, congress=119)
        mock_summary.assert_called_once()

    @patch.object(run_hearings, "run_hearings_sync")
    @patch.object(run_hearings, "print_summary")
    @patch.object(run_hearings, "init_db")
    def test_full_flag(self, mock_init, mock_summary, mock_sync):
        with patch("sys.argv", ["prog", "--full"]):
            run_hearings.main()
        mock_sync.assert_called_once_with(full=True, congress=119)

    @patch.object(run_hearings, "run_hearings_sync")
    @patch.object(run_hearings, "print_summary")
    @patch.object(run_hearings, "init_db")
    def test_congress_flag(self, mock_init, mock_summary, mock_sync):
        with patch("sys.argv", ["prog", "--congress", "118"]):
            run_hearings.main()
        mock_sync.assert_called_once_with(full=False, congress=118)

    @patch.object(run_hearings, "print_summary")
    @patch.object(run_hearings, "init_db")
    def test_summary_only(self, mock_init, mock_summary):
        with patch("sys.argv", ["prog", "--summary"]):
            run_hearings.main()
        mock_summary.assert_called_once()


# ── run_hearings_sync ────────────────────────────────────────────

class TestRunHearingsSync:
    @patch.object(run_hearings, "send_error_alert")
    @patch.object(run_hearings, "sync_va_hearings")
    def test_success_path(self, mock_sync, mock_alert, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(run_hearings, "ROOT", tmp_path)
        _make_schema_file(tmp_path)
        mock_sync.return_value = {
            "new_hearings": 2, "updated_hearings": 1, "changes": [{"field": "status"}], "errors": [],
        }

        result = run_hearings.run_hearings_sync(full=False, congress=119)

        assert result["status"] == "SUCCESS"
        assert result["source_id"] == "congress_hearings"
        mock_alert.assert_not_called()

        output = capsys.readouterr().out
        assert "new_hearings_count" in output

    @patch.object(run_hearings, "send_error_alert")
    @patch.object(run_hearings, "sync_va_hearings")
    def test_exception_path(self, mock_sync, mock_alert, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(run_hearings, "ROOT", tmp_path)
        _make_schema_file(tmp_path)
        mock_sync.side_effect = ConnectionError("Timeout")

        result = run_hearings.run_hearings_sync()

        assert result["status"] == "ERROR"
        assert any("Timeout" in e for e in result["errors"])
        mock_alert.assert_called_once()

    @patch.object(run_hearings, "send_error_alert")
    @patch.object(run_hearings, "sync_va_hearings")
    def test_no_data_path(self, mock_sync, mock_alert, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(run_hearings, "ROOT", tmp_path)
        _make_schema_file(tmp_path)
        mock_sync.return_value = {
            "new_hearings": 0, "updated_hearings": 0, "changes": [], "errors": [],
        }

        result = run_hearings.run_hearings_sync()
        assert result["status"] == "NO_DATA"

    @patch.object(run_hearings, "send_error_alert")
    @patch.object(run_hearings, "sync_va_hearings")
    def test_sync_errors_status(self, mock_sync, mock_alert, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(run_hearings, "ROOT", tmp_path)
        _make_schema_file(tmp_path)
        mock_sync.return_value = {
            "new_hearings": 1, "updated_hearings": 0, "changes": [],
            "errors": ["Rate limited"],
        }

        result = run_hearings.run_hearings_sync()
        assert result["status"] == "ERROR"

    @patch.object(run_hearings, "send_error_alert")
    @patch.object(run_hearings, "sync_va_hearings")
    def test_full_sync_higher_limit(self, mock_sync, mock_alert, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(run_hearings, "ROOT", tmp_path)
        _make_schema_file(tmp_path)
        mock_sync.return_value = {
            "new_hearings": 0, "updated_hearings": 0, "changes": [], "errors": [],
        }

        run_hearings.run_hearings_sync(full=True)
        call_kwargs = mock_sync.call_args[1]
        assert call_kwargs["limit"] == 250


# ── print_summary ────────────────────────────────────────────────

class TestPrintSummary:
    def test_empty_db_summary(self, capsys):
        run_hearings.print_summary()
        output = capsys.readouterr().out
        assert "VA HEARINGS TRACKING" in output
        assert "Total hearings tracked:" in output

    def test_populated_summary(self, capsys):
        _insert_test_hearing()
        run_hearings.print_summary()
        output = capsys.readouterr().out
        assert "Upcoming Hearings:" in output

    def test_summary_committee_display(self, capsys):
        _insert_test_hearing(event_id="E-H1", committee_code="hsvr00")
        _insert_test_hearing(event_id="E-S1", committee_code="ssva00")
        run_hearings.print_summary()
        output = capsys.readouterr().out
        assert "HVAC" in output or "SVAC" in output

    def test_summary_long_title_truncated(self, capsys):
        _insert_test_hearing(event_id="E-LT", title="A" * 100)
        run_hearings.print_summary()
        output = capsys.readouterr().out
        assert "..." in output

    def test_summary_status_display(self, capsys):
        _insert_test_hearing(event_id="E-PP", status="postponed")
        run_hearings.print_summary()
        output = capsys.readouterr().out
        assert "[postponed]" in output


# ── write_run_record ─────────────────────────────────────────────

class TestWriteRunRecord:
    def test_writes_json_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(run_hearings, "ROOT", tmp_path)
        record = {"source_id": "test", "status": "SUCCESS"}
        run_hearings.write_run_record(record)
        output_dir = tmp_path / "outputs" / "runs"
        files = list(output_dir.glob("HEARINGS_*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text())
        assert data["source_id"] == "test"


# ── load_run_schema ──────────────────────────────────────────────

class TestLoadRunSchema:
    def test_loads_schema(self):
        schema = run_hearings.load_run_schema()
        assert "properties" in schema
        assert "source_id" in schema["properties"]
