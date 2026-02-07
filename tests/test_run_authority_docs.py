"""Tests for src/run_authority_docs.py — CLI runner for authority document collection."""

import json
from unittest.mock import MagicMock, patch

import pytest

from src import run_authority_docs

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

FAKE_DOC = {
    "doc_id": "WH-2024-001",
    "title": "Executive Order on Veterans Affairs",
    "source_url": "https://whitehouse.gov/eo-2024-001",
    "authority_type": "executive_order",
    "published_date": "2024-01-15",
    "body": "Full text of executive order...",
}


def _setup_schema(tmp_path, monkeypatch):
    monkeypatch.setattr(run_authority_docs, "ROOT", tmp_path)
    schemas_dir = tmp_path / "schemas"
    schemas_dir.mkdir()
    (schemas_dir / "source_run.schema.json").write_text(SCHEMA_JSON)


# ── run_source ───────────────────────────────────────────────────


class TestRunSource:
    @patch.object(run_authority_docs, "upsert_authority_doc")
    def test_success_with_new_docs(self, mock_upsert):
        mock_fetch = MagicMock(return_value=[FAKE_DOC])
        mock_upsert.return_value = True  # new doc

        orig_fn = run_authority_docs.AUTHORITY_SOURCES["whitehouse"]["fetch_fn"]
        run_authority_docs.AUTHORITY_SOURCES["whitehouse"]["fetch_fn"] = mock_fetch
        try:
            run_record, new_docs = run_authority_docs.run_source("whitehouse")
        finally:
            run_authority_docs.AUTHORITY_SOURCES["whitehouse"]["fetch_fn"] = orig_fn

        assert run_record["status"] == "SUCCESS"
        assert run_record["source_id"] == "authority_whitehouse"
        assert run_record["records_fetched"] == 1
        assert len(new_docs) == 1
        assert new_docs[0]["doc_id"] == "WH-2024-001"

    @patch.object(run_authority_docs, "upsert_authority_doc")
    def test_success_no_new_docs(self, mock_upsert):
        mock_fetch = MagicMock(return_value=[FAKE_DOC])
        mock_upsert.return_value = False  # already seen

        orig_fn = run_authority_docs.AUTHORITY_SOURCES["whitehouse"]["fetch_fn"]
        run_authority_docs.AUTHORITY_SOURCES["whitehouse"]["fetch_fn"] = mock_fetch
        try:
            run_record, new_docs = run_authority_docs.run_source("whitehouse")
        finally:
            run_authority_docs.AUTHORITY_SOURCES["whitehouse"]["fetch_fn"] = orig_fn

        assert run_record["status"] == "NO_DATA"
        assert run_record["records_fetched"] == 1
        assert len(new_docs) == 0

    def test_no_data_empty_fetch(self):
        mock_fetch = MagicMock(return_value=[])

        orig_fn = run_authority_docs.AUTHORITY_SOURCES["whitehouse"]["fetch_fn"]
        run_authority_docs.AUTHORITY_SOURCES["whitehouse"]["fetch_fn"] = mock_fetch
        try:
            run_record, new_docs = run_authority_docs.run_source("whitehouse")
        finally:
            run_authority_docs.AUTHORITY_SOURCES["whitehouse"]["fetch_fn"] = orig_fn

        assert run_record["status"] == "NO_DATA"
        assert run_record["records_fetched"] == 0

    def test_error_on_exception(self):
        mock_fetch = MagicMock(side_effect=RuntimeError("API down"))

        orig_fn = run_authority_docs.AUTHORITY_SOURCES["whitehouse"]["fetch_fn"]
        run_authority_docs.AUTHORITY_SOURCES["whitehouse"]["fetch_fn"] = mock_fetch
        try:
            run_record, new_docs = run_authority_docs.run_source("whitehouse")
        finally:
            run_authority_docs.AUTHORITY_SOURCES["whitehouse"]["fetch_fn"] = orig_fn

        assert run_record["status"] == "ERROR"
        assert any("API down" in e for e in run_record["errors"])

    def test_unknown_source_raises(self):
        with pytest.raises(ValueError, match="Unknown source"):
            run_authority_docs.run_source("nonexistent")

    @patch.object(run_authority_docs, "upsert_authority_doc")
    def test_omb_source(self, mock_upsert):
        mock_fetch = MagicMock(return_value=[FAKE_DOC])
        mock_upsert.return_value = True

        orig_fn = run_authority_docs.AUTHORITY_SOURCES["omb"]["fetch_fn"]
        run_authority_docs.AUTHORITY_SOURCES["omb"]["fetch_fn"] = mock_fetch
        try:
            run_record, new_docs = run_authority_docs.run_source("omb")
        finally:
            run_authority_docs.AUTHORITY_SOURCES["omb"]["fetch_fn"] = orig_fn

        assert run_record["source_id"] == "authority_omb"
        assert run_record["status"] == "SUCCESS"

    @patch.object(run_authority_docs, "upsert_authority_doc")
    def test_va_source(self, mock_upsert):
        mock_fetch = MagicMock(return_value=[FAKE_DOC])
        mock_upsert.return_value = True

        orig_fn = run_authority_docs.AUTHORITY_SOURCES["va"]["fetch_fn"]
        run_authority_docs.AUTHORITY_SOURCES["va"]["fetch_fn"] = mock_fetch
        try:
            run_record, new_docs = run_authority_docs.run_source("va")
        finally:
            run_authority_docs.AUTHORITY_SOURCES["va"]["fetch_fn"] = orig_fn

        assert run_record["source_id"] == "authority_va"
        assert run_record["status"] == "SUCCESS"

    @patch.object(run_authority_docs, "upsert_authority_doc")
    def test_upsert_error_captured(self, mock_upsert):
        mock_fetch = MagicMock(return_value=[FAKE_DOC])
        mock_upsert.side_effect = RuntimeError("DB write failed")

        orig_fn = run_authority_docs.AUTHORITY_SOURCES["whitehouse"]["fetch_fn"]
        run_authority_docs.AUTHORITY_SOURCES["whitehouse"]["fetch_fn"] = mock_fetch
        try:
            run_record, new_docs = run_authority_docs.run_source("whitehouse")
        finally:
            run_authority_docs.AUTHORITY_SOURCES["whitehouse"]["fetch_fn"] = orig_fn

        # Upsert errors are captured per-doc, not top-level
        assert len(run_record["errors"]) == 1
        assert "DB write failed" in run_record["errors"][0]


# ── run_authority_docs (aggregate) ───────────────────────────────


class TestRunAuthorityDocs:
    @patch.object(run_authority_docs, "send_new_docs_alert")
    @patch.object(run_authority_docs, "send_error_alert")
    @patch.object(run_authority_docs, "run_source")
    def test_aggregate_success(
        self, mock_run_source, mock_err_alert, mock_docs_alert, tmp_path, monkeypatch, capsys
    ):
        _setup_schema(tmp_path, monkeypatch)
        mock_run_source.return_value = (
            {
                "source_id": "authority_whitehouse",
                "started_at": "2024-01-01T00:00:00Z",
                "ended_at": "2024-01-01T00:01:00Z",
                "status": "SUCCESS",
                "records_fetched": 2,
                "errors": [],
            },
            [
                {
                    "doc_id": "WH-001",
                    "title": "Test",
                    "source_url": "https://example.com",
                    "authority_type": "eo",
                }
            ],
        )

        result = run_authority_docs.run_authority_docs.__wrapped__(sources=["whitehouse"])

        assert result["status"] == "SUCCESS"
        assert result["source_id"] == "authority_aggregate"
        mock_err_alert.assert_not_called()
        mock_docs_alert.assert_called_once()

    @patch.object(run_authority_docs, "send_new_docs_alert")
    @patch.object(run_authority_docs, "send_error_alert")
    @patch.object(run_authority_docs, "run_source")
    def test_aggregate_all_error(
        self, mock_run_source, mock_err_alert, mock_docs_alert, tmp_path, monkeypatch, capsys
    ):
        _setup_schema(tmp_path, monkeypatch)
        mock_run_source.side_effect = RuntimeError("Total failure")

        result = run_authority_docs.run_authority_docs.__wrapped__(sources=["whitehouse"])

        assert result["status"] == "ERROR"
        mock_err_alert.assert_called_once()

    @patch.object(run_authority_docs, "send_new_docs_alert")
    @patch.object(run_authority_docs, "send_error_alert")
    @patch.object(run_authority_docs, "run_source")
    def test_aggregate_no_data(
        self, mock_run_source, mock_err_alert, mock_docs_alert, tmp_path, monkeypatch, capsys
    ):
        _setup_schema(tmp_path, monkeypatch)
        mock_run_source.return_value = (
            {
                "source_id": "authority_whitehouse",
                "started_at": "2024-01-01T00:00:00Z",
                "ended_at": "2024-01-01T00:01:00Z",
                "status": "NO_DATA",
                "records_fetched": 0,
                "errors": [],
            },
            [],
        )

        result = run_authority_docs.run_authority_docs.__wrapped__(sources=["whitehouse"])

        assert result["status"] == "NO_DATA"

    @patch.object(run_authority_docs, "send_new_docs_alert")
    @patch.object(run_authority_docs, "send_error_alert")
    @patch.object(run_authority_docs, "run_source")
    def test_aggregate_mixed_status(
        self, mock_run_source, mock_err_alert, mock_docs_alert, tmp_path, monkeypatch, capsys
    ):
        """When some sources succeed and some fail, overall is SUCCESS."""
        _setup_schema(tmp_path, monkeypatch)
        call_count = 0

        def _side_effect(source_id):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (
                    {
                        "source_id": f"authority_{source_id}",
                        "started_at": "2024-01-01T00:00:00Z",
                        "ended_at": "2024-01-01T00:01:00Z",
                        "status": "SUCCESS",
                        "records_fetched": 1,
                        "errors": [],
                    },
                    [
                        {
                            "doc_id": "DOC-1",
                            "title": "Test",
                            "source_url": "https://example.com",
                            "authority_type": "eo",
                        }
                    ],
                )
            else:
                raise RuntimeError("Source 2 failed")

        mock_run_source.side_effect = _side_effect

        result = run_authority_docs.run_authority_docs.__wrapped__(sources=["whitehouse", "omb"])

        assert result["status"] == "SUCCESS"


# ── main (argument parsing) ──────────────────────────────────────


class TestMainArgParsing:
    @patch.object(run_authority_docs, "run_authority_docs")
    def test_list_sources(self, mock_run, capsys):
        with patch("sys.argv", ["prog", "--list-sources"]):
            run_authority_docs.main()
        output = capsys.readouterr().out
        assert "whitehouse" in output
        assert "omb" in output
        mock_run.assert_not_called()

    @patch.object(run_authority_docs, "run_authority_docs")
    def test_run_specific_source(self, mock_run):
        mock_run.return_value = {"status": "SUCCESS"}
        with patch("sys.argv", ["prog", "--source", "whitehouse"]):
            run_authority_docs.main()
        mock_run.assert_called_once_with(["whitehouse"])

    @patch.object(run_authority_docs, "run_authority_docs")
    def test_run_all_sources(self, mock_run):
        mock_run.return_value = {"status": "SUCCESS"}
        with patch("sys.argv", ["prog", "--all"]):
            run_authority_docs.main()
        mock_run.assert_called_once_with(None)

    @patch.object(run_authority_docs, "run_authority_docs")
    def test_default_runs_all(self, mock_run):
        mock_run.return_value = {"status": "SUCCESS"}
        with patch("sys.argv", ["prog"]):
            run_authority_docs.main()
        mock_run.assert_called_once_with(None)


# ── write_run_record ─────────────────────────────────────────────


class TestWriteRunRecord:
    def test_writes_json_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(run_authority_docs, "ROOT", tmp_path)
        record = {"source_id": "authority_whitehouse", "status": "SUCCESS"}
        run_authority_docs.write_run_record(record, "whitehouse")
        output_dir = tmp_path / "outputs" / "runs"
        files = list(output_dir.glob("AUTHORITY_WHITEHOUSE_*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text())
        assert data["source_id"] == "authority_whitehouse"


# ── load_run_schema ──────────────────────────────────────────────


class TestLoadRunSchema:
    def test_loads_schema(self):
        schema = run_authority_docs.load_run_schema()
        assert "properties" in schema
        assert "source_id" in schema["properties"]

    def test_fallback_when_missing(self, tmp_path, monkeypatch):
        """When schema file doesn't exist, returns a minimal fallback schema."""
        monkeypatch.setattr(run_authority_docs, "ROOT", tmp_path)
        schema = run_authority_docs.load_run_schema()
        assert "properties" in schema
