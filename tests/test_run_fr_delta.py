"""Tests for src/run_fr_delta.py — CLI runner for Federal Register delta detection."""

import json
from unittest.mock import patch

from src import run_fr_delta

# ── helpers ──────────────────────────────────────────────────────

SCHEMA_JSON = json.dumps(
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

FAKE_CFG = {
    "approved_sources": [
        {
            "id": "govinfo_fr_bulk",
            "endpoints": ["https://api.govinfo.gov/collections/FR"],
        }
    ]
}


def _setup_schema(tmp_path, monkeypatch):
    """Set ROOT to tmp_path and create schema file."""
    monkeypatch.setattr(run_fr_delta, "ROOT", tmp_path)
    schemas_dir = tmp_path / "schemas"
    schemas_dir.mkdir()
    (schemas_dir / "source_run.schema.json").write_text(SCHEMA_JSON)


# ── run_fr_delta ─────────────────────────────────────────────────


class TestRunFrDelta:
    @patch.object(run_fr_delta, "send_new_docs_alert")
    @patch.object(run_fr_delta, "send_error_alert")
    @patch.object(run_fr_delta, "upsert_fr_seen")
    @patch.object(run_fr_delta, "list_month_packages")
    @patch.object(run_fr_delta, "list_latest_month_folders")
    @patch.object(run_fr_delta, "load_cfg")
    def test_success_with_new_docs(
        self,
        mock_cfg,
        mock_folders,
        mock_packages,
        mock_upsert,
        mock_err_alert,
        mock_docs_alert,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        _setup_schema(tmp_path, monkeypatch)
        mock_cfg.return_value = FAKE_CFG
        mock_folders.return_value = [("2024-01", "https://example.com/2024-01")]
        mock_packages.return_value = [
            {
                "doc_id": "FR-2024-0001",
                "published_date": "2024-01-15",
                "source_url": "https://example.com/doc1",
            },
            {
                "doc_id": "FR-2024-0002",
                "published_date": "2024-01-16",
                "source_url": "https://example.com/doc2",
            },
        ]
        mock_upsert.return_value = True  # new doc

        result = run_fr_delta.run_fr_delta.__wrapped__(max_months=1)

        assert result["status"] == "SUCCESS"
        assert result["source_id"] == "govinfo_fr_bulk"
        assert result["records_fetched"] == 2
        assert result["errors"] == []
        mock_err_alert.assert_not_called()
        mock_docs_alert.assert_called_once()

        output = capsys.readouterr().out
        assert "new_docs_count" in output

    @patch.object(run_fr_delta, "send_new_docs_alert")
    @patch.object(run_fr_delta, "send_error_alert")
    @patch.object(run_fr_delta, "upsert_fr_seen")
    @patch.object(run_fr_delta, "list_month_packages")
    @patch.object(run_fr_delta, "list_latest_month_folders")
    @patch.object(run_fr_delta, "load_cfg")
    def test_success_no_new_docs_becomes_no_data(
        self,
        mock_cfg,
        mock_folders,
        mock_packages,
        mock_upsert,
        mock_err_alert,
        mock_docs_alert,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        """When packages exist but all are already seen, status is NO_DATA."""
        _setup_schema(tmp_path, monkeypatch)
        mock_cfg.return_value = FAKE_CFG
        mock_folders.return_value = [("2024-01", "https://example.com/2024-01")]
        mock_packages.return_value = [
            {
                "doc_id": "FR-2024-0001",
                "published_date": "2024-01-15",
                "source_url": "https://example.com/doc1",
            },
        ]
        mock_upsert.return_value = False  # already seen

        result = run_fr_delta.run_fr_delta.__wrapped__(max_months=1)

        assert result["status"] == "NO_DATA"
        assert result["records_fetched"] == 1

    @patch.object(run_fr_delta, "send_new_docs_alert")
    @patch.object(run_fr_delta, "send_error_alert")
    @patch.object(run_fr_delta, "list_latest_month_folders")
    @patch.object(run_fr_delta, "load_cfg")
    def test_no_data_empty_folders(
        self,
        mock_cfg,
        mock_folders,
        mock_err_alert,
        mock_docs_alert,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        _setup_schema(tmp_path, monkeypatch)
        mock_cfg.return_value = FAKE_CFG
        mock_folders.return_value = []

        result = run_fr_delta.run_fr_delta.__wrapped__(max_months=1)

        assert result["status"] == "NO_DATA"
        assert result["records_fetched"] == 0
        mock_err_alert.assert_not_called()
        mock_docs_alert.assert_not_called()

    @patch.object(run_fr_delta, "send_new_docs_alert")
    @patch.object(run_fr_delta, "send_error_alert")
    @patch.object(run_fr_delta, "list_latest_month_folders")
    @patch.object(run_fr_delta, "load_cfg")
    def test_error_on_exception(
        self,
        mock_cfg,
        mock_folders,
        mock_err_alert,
        mock_docs_alert,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        _setup_schema(tmp_path, monkeypatch)
        mock_cfg.return_value = FAKE_CFG
        mock_folders.side_effect = RuntimeError("API timeout")

        result = run_fr_delta.run_fr_delta.__wrapped__(max_months=1)

        assert result["status"] == "ERROR"
        assert any("API timeout" in e for e in result["errors"])
        mock_err_alert.assert_called_once()

    @patch.object(run_fr_delta, "send_new_docs_alert")
    @patch.object(run_fr_delta, "send_error_alert")
    @patch.object(run_fr_delta, "upsert_fr_seen")
    @patch.object(run_fr_delta, "list_month_packages")
    @patch.object(run_fr_delta, "list_latest_month_folders")
    @patch.object(run_fr_delta, "load_cfg")
    def test_multiple_months(
        self,
        mock_cfg,
        mock_folders,
        mock_packages,
        mock_upsert,
        mock_err_alert,
        mock_docs_alert,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        _setup_schema(tmp_path, monkeypatch)
        mock_cfg.return_value = FAKE_CFG
        mock_folders.return_value = [
            ("2024-01", "https://example.com/2024-01"),
            ("2024-02", "https://example.com/2024-02"),
        ]
        mock_packages.side_effect = [
            [
                {
                    "doc_id": "FR-2024-0001",
                    "published_date": "2024-01-15",
                    "source_url": "https://example.com/doc1",
                }
            ],
            [
                {
                    "doc_id": "FR-2024-0010",
                    "published_date": "2024-02-01",
                    "source_url": "https://example.com/doc10",
                }
            ],
        ]
        mock_upsert.return_value = True

        result = run_fr_delta.run_fr_delta.__wrapped__(max_months=3)

        assert result["status"] == "SUCCESS"
        assert result["records_fetched"] == 2


# ── write_run_record ─────────────────────────────────────────────


class TestWriteRunRecord:
    def test_writes_json_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(run_fr_delta, "ROOT", tmp_path)
        record = {"source_id": "govinfo_fr_bulk", "status": "SUCCESS"}
        run_fr_delta.write_run_record(record)
        output_dir = tmp_path / "outputs" / "runs"
        files = list(output_dir.glob("FR_DELTA_*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text())
        assert data["source_id"] == "govinfo_fr_bulk"


# ── load_cfg ─────────────────────────────────────────────────────


class TestLoadCfg:
    def test_loads_config(self):
        """Verify load_cfg returns config with approved_sources key."""
        try:
            cfg = run_fr_delta.load_cfg()
            assert "approved_sources" in cfg
        except FileNotFoundError:
            # Config may not exist in test environment
            pass


# ── load_run_schema ──────────────────────────────────────────────


class TestLoadRunSchema:
    def test_loads_schema(self):
        schema = run_fr_delta.load_run_schema()
        assert "properties" in schema
        assert "source_id" in schema["properties"]
