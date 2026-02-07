"""Tests for src/run_bills.py — CLI runner for VA Bills sync."""

import json
from unittest.mock import patch

import src.db as db
from src import run_bills

# ── helpers ──────────────────────────────────────────────────────


def _insert_test_bill():
    db.upsert_bill(
        {
            "bill_id": "hr-118-100",
            "congress": 118,
            "bill_type": "hr",
            "bill_number": 100,
            "title": "Test VA Bill",
            "sponsor_name": "Smith",
            "sponsor_bioguide_id": "S000001",
            "sponsor_party": "D",
            "sponsor_state": "CA",
            "introduced_date": "2024-01-10",
            "latest_action_date": "2024-02-15",
            "latest_action_text": "Introduced",
            "policy_area": "Veterans",
            "committees_json": "[]",
            "cosponsors_count": 3,
        }
    )


# ── Argument parsing ─────────────────────────────────────────────


class TestMainArgParsing:
    @patch.object(run_bills, "run_bills_sync")
    @patch.object(run_bills, "print_summary")
    @patch.object(run_bills, "init_db")
    def test_default_runs_sync(self, mock_init, mock_summary, mock_sync):
        with patch("sys.argv", ["prog"]):
            run_bills.main()
        mock_sync.assert_called_once_with(full=False, congress=118)
        mock_summary.assert_called_once()

    @patch.object(run_bills, "run_bills_sync")
    @patch.object(run_bills, "print_summary")
    @patch.object(run_bills, "init_db")
    def test_full_flag(self, mock_init, mock_summary, mock_sync):
        with patch("sys.argv", ["prog", "--full"]):
            run_bills.main()
        mock_sync.assert_called_once_with(full=True, congress=118)

    @patch.object(run_bills, "run_bills_sync")
    @patch.object(run_bills, "print_summary")
    @patch.object(run_bills, "init_db")
    def test_congress_flag(self, mock_init, mock_summary, mock_sync):
        with patch("sys.argv", ["prog", "--congress", "119"]):
            run_bills.main()
        mock_sync.assert_called_once_with(full=False, congress=119)

    @patch.object(run_bills, "print_summary")
    @patch.object(run_bills, "init_db")
    def test_summary_only(self, mock_init, mock_summary):
        with patch("sys.argv", ["prog", "--summary"]):
            run_bills.main()
        mock_summary.assert_called_once()


# ── run_bills_sync ───────────────────────────────────────────────


class TestRunBillsSync:
    @patch.object(run_bills, "send_error_alert")
    @patch.object(run_bills, "sync_va_bills")
    def test_success_path(self, mock_sync, mock_alert, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(run_bills, "ROOT", tmp_path)
        mock_sync.return_value = {
            "new_bills": 3,
            "new_actions": 5,
            "updated_bills": 1,
            "errors": [],
        }

        # Need schema file for validation
        schemas_dir = tmp_path / "schemas"
        schemas_dir.mkdir()
        (schemas_dir / "source_run.schema.json").write_text(
            json.dumps(
                {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "required": [
                        "source_id",
                        "started_at",
                        "ended_at",
                        "status",
                        "records_fetched",
                        "errors",
                    ],
                    "properties": {
                        "source_id": {"type": "string"},
                        "started_at": {"type": "string"},
                        "ended_at": {"type": "string"},
                        "status": {"type": "string", "enum": ["SUCCESS", "NO_DATA", "ERROR"]},
                        "records_fetched": {"type": "integer", "minimum": 0},
                        "errors": {"type": "array", "items": {"type": "string"}},
                    },
                }
            )
        )

        result = run_bills.run_bills_sync(full=False, congress=118)

        assert result["status"] == "SUCCESS"
        assert result["source_id"] == "congress_bills"
        mock_alert.assert_not_called()

        output = capsys.readouterr().out
        assert "new_bills_count" in output

    @patch.object(run_bills, "send_error_alert")
    @patch.object(run_bills, "sync_va_bills")
    def test_exception_path(self, mock_sync, mock_alert, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(run_bills, "ROOT", tmp_path)
        mock_sync.side_effect = RuntimeError("API down")

        schemas_dir = tmp_path / "schemas"
        schemas_dir.mkdir()
        (schemas_dir / "source_run.schema.json").write_text(
            json.dumps(
                {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "required": [
                        "source_id",
                        "started_at",
                        "ended_at",
                        "status",
                        "records_fetched",
                        "errors",
                    ],
                    "properties": {
                        "source_id": {"type": "string"},
                        "started_at": {"type": "string"},
                        "ended_at": {"type": "string"},
                        "status": {"type": "string", "enum": ["SUCCESS", "NO_DATA", "ERROR"]},
                        "records_fetched": {"type": "integer", "minimum": 0},
                        "errors": {"type": "array", "items": {"type": "string"}},
                    },
                }
            )
        )

        result = run_bills.run_bills_sync()

        assert result["status"] == "ERROR"
        assert any("API down" in e for e in result["errors"])
        mock_alert.assert_called_once()

    @patch.object(run_bills, "send_error_alert")
    @patch.object(run_bills, "sync_va_bills")
    def test_no_data_path(self, mock_sync, mock_alert, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(run_bills, "ROOT", tmp_path)
        mock_sync.return_value = {
            "new_bills": 0,
            "new_actions": 0,
            "updated_bills": 0,
            "errors": [],
        }

        schemas_dir = tmp_path / "schemas"
        schemas_dir.mkdir()
        (schemas_dir / "source_run.schema.json").write_text(
            json.dumps(
                {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "required": [
                        "source_id",
                        "started_at",
                        "ended_at",
                        "status",
                        "records_fetched",
                        "errors",
                    ],
                    "properties": {
                        "source_id": {"type": "string"},
                        "started_at": {"type": "string"},
                        "ended_at": {"type": "string"},
                        "status": {"type": "string", "enum": ["SUCCESS", "NO_DATA", "ERROR"]},
                        "records_fetched": {"type": "integer", "minimum": 0},
                        "errors": {"type": "array", "items": {"type": "string"}},
                    },
                }
            )
        )

        result = run_bills.run_bills_sync()
        assert result["status"] == "NO_DATA"

    @patch.object(run_bills, "send_error_alert")
    @patch.object(run_bills, "sync_va_bills")
    def test_sync_errors_status(self, mock_sync, mock_alert, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(run_bills, "ROOT", tmp_path)
        mock_sync.return_value = {
            "new_bills": 2,
            "new_actions": 0,
            "updated_bills": 0,
            "errors": ["Rate limited on page 3"],
        }

        schemas_dir = tmp_path / "schemas"
        schemas_dir.mkdir()
        (schemas_dir / "source_run.schema.json").write_text(
            json.dumps(
                {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "required": [
                        "source_id",
                        "started_at",
                        "ended_at",
                        "status",
                        "records_fetched",
                        "errors",
                    ],
                    "properties": {
                        "source_id": {"type": "string"},
                        "started_at": {"type": "string"},
                        "ended_at": {"type": "string"},
                        "status": {"type": "string", "enum": ["SUCCESS", "NO_DATA", "ERROR"]},
                        "records_fetched": {"type": "integer", "minimum": 0},
                        "errors": {"type": "array", "items": {"type": "string"}},
                    },
                }
            )
        )

        result = run_bills.run_bills_sync()
        assert result["status"] == "ERROR"


# ── print_summary ────────────────────────────────────────────────


class TestPrintSummary:
    def test_empty_db_summary(self, capsys):
        run_bills.print_summary()
        output = capsys.readouterr().out
        assert "VA BILLS TRACKING" in output
        assert "Total bills tracked:" in output

    def test_populated_summary(self, capsys):
        _insert_test_bill()
        run_bills.print_summary()
        output = capsys.readouterr().out
        assert "Test VA Bill" in output or "hr 100" in output


# ── write_run_record ─────────────────────────────────────────────


class TestWriteRunRecord:
    def test_writes_json_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(run_bills, "ROOT", tmp_path)
        record = {"source_id": "test", "status": "SUCCESS"}
        run_bills.write_run_record(record)
        output_dir = tmp_path / "outputs" / "runs"
        files = list(output_dir.glob("BILLS_*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text())
        assert data["source_id"] == "test"


# ── load_run_schema ──────────────────────────────────────────────


class TestLoadRunSchema:
    def test_loads_schema(self):
        schema = run_bills.load_run_schema()
        assert "properties" in schema
        assert "source_id" in schema["properties"]
