"""Tests for report generation and export (src/reports.py)."""

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from src.reports import (
    _aggregate_run_stats,
    _assess_urgency,
    _build_report_highlights,
    _escape_csv_field,
    _filter_va_docs,
    _format_highlights,
    _get_period_bounds,
    _parse_iso_date,
    _parse_iso_datetime,
    _shape_fr_document,
    export_csv,
    export_json,
    generate_report,
)

# ---------------------------------------------------------------------------
# _parse_iso_datetime
# ---------------------------------------------------------------------------


class TestParseIsoDatetime:
    def test_parses_utc_z(self):
        result = _parse_iso_datetime("2024-01-15T10:30:00Z")
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 10
        assert result.minute == 30

    def test_parses_offset(self):
        result = _parse_iso_datetime("2024-06-01T08:00:00+00:00")
        assert result.year == 2024
        assert result.month == 6


# ---------------------------------------------------------------------------
# _get_period_bounds
# ---------------------------------------------------------------------------


class TestGetPeriodBounds:
    def test_daily_returns_24h(self):
        start, end = _get_period_bounds("daily")
        diff = end - start
        assert abs(diff.total_seconds() - 86400) < 5  # ~24h within tolerance

    def test_weekly_returns_7d(self):
        start, end = _get_period_bounds("weekly")
        diff = end - start
        assert abs(diff.days - 7) <= 1

    def test_custom_with_dates(self):
        start, end = _get_period_bounds("custom", "2024-01-01", "2024-01-15")
        assert start.year == 2024
        assert start.month == 1
        assert start.day == 1
        assert end.day == 15

    def test_invalid_type_raises(self):
        with pytest.raises(ValueError, match="Unknown report_type"):
            _get_period_bounds("invalid")

    def test_custom_without_dates_raises(self):
        with pytest.raises(ValueError, match="Custom reports require"):
            _get_period_bounds("custom")

    def test_custom_missing_end_raises(self):
        with pytest.raises(ValueError, match="Custom reports require"):
            _get_period_bounds("custom", start_date="2024-01-01")


# ---------------------------------------------------------------------------
# _aggregate_run_stats
# ---------------------------------------------------------------------------


class TestAggregateRunStats:
    def test_empty_runs(self):
        result = _aggregate_run_stats([])
        assert result["total_runs"] == 0
        assert result["successful_runs"] == 0
        assert result["error_runs"] == 0
        assert result["no_data_runs"] == 0
        assert result["sources"] == {}

    def test_mixed_statuses(self):
        runs = [
            {"source_id": "fr", "status": "SUCCESS", "records_fetched": 5},
            {"source_id": "fr", "status": "ERROR", "records_fetched": 0},
            {"source_id": "bills", "status": "NO_DATA", "records_fetched": 0},
            {"source_id": "bills", "status": "SUCCESS", "records_fetched": 10},
        ]
        result = _aggregate_run_stats(runs)
        assert result["total_runs"] == 4
        assert result["successful_runs"] == 2
        assert result["error_runs"] == 1
        assert result["no_data_runs"] == 1
        assert result["sources"]["fr"]["total_runs"] == 2
        assert result["sources"]["fr"]["total_records_fetched"] == 5
        assert result["sources"]["bills"]["successful_runs"] == 1

    def test_single_source(self):
        runs = [
            {"source_id": "ecfr", "status": "SUCCESS", "records_fetched": 3},
        ]
        result = _aggregate_run_stats(runs)
        assert result["total_runs"] == 1
        assert result["sources"]["ecfr"]["total_records_fetched"] == 3


# ---------------------------------------------------------------------------
# _parse_iso_date
# ---------------------------------------------------------------------------


class TestParseIsoDate:
    def test_valid_date(self):
        result = _parse_iso_date("2024-01-15")
        assert result == date(2024, 1, 15)

    def test_none_returns_none(self):
        assert _parse_iso_date(None) is None

    def test_empty_string_returns_none(self):
        assert _parse_iso_date("") is None

    def test_invalid_string_returns_none(self):
        assert _parse_iso_date("not-a-date") is None

    def test_datetime_string_extracts_date(self):
        result = _parse_iso_date("2024-06-15T10:30:00Z")
        assert result == date(2024, 6, 15)


# ---------------------------------------------------------------------------
# _assess_urgency
# ---------------------------------------------------------------------------


class TestAssessUrgency:
    def test_close_comment_deadline_is_urgent(self):
        today = date(2024, 6, 15)
        entry = {"comments_close_on": "2024-06-20"}
        is_urgent, reasons = _assess_urgency(entry, today)
        assert is_urgent is True
        assert len(reasons) == 1
        assert "close" in reasons[0].lower()

    def test_no_deadlines_not_urgent(self):
        today = date(2024, 6, 15)
        entry = {}
        is_urgent, reasons = _assess_urgency(entry, today)
        assert is_urgent is False
        assert reasons == []

    def test_effective_date_soon_is_urgent(self):
        today = date(2024, 6, 15)
        entry = {"effective_on": "2024-06-25"}
        is_urgent, reasons = _assess_urgency(entry, today)
        assert is_urgent is True
        assert "effective" in reasons[0].lower()

    def test_far_deadline_not_urgent(self):
        today = date(2024, 6, 15)
        entry = {"comments_close_on": "2024-12-31"}
        is_urgent, reasons = _assess_urgency(entry, today)
        assert is_urgent is False

    def test_past_deadline_not_urgent(self):
        today = date(2024, 6, 15)
        entry = {"comments_close_on": "2024-05-01"}
        is_urgent, reasons = _assess_urgency(entry, today)
        assert is_urgent is False


# ---------------------------------------------------------------------------
# _filter_va_docs
# ---------------------------------------------------------------------------


class TestFilterVaDocs:
    def test_filters_va_only(self):
        docs = [
            {"agencies": ["Department of Veterans Affairs"]},
            {"agencies": ["Department of Defense"]},
            {"agencies": ["Department of Veterans Affairs", "OMB"]},
        ]
        result = _filter_va_docs(docs)
        assert len(result) == 2

    def test_empty_list(self):
        assert _filter_va_docs([]) == []

    def test_no_va_docs(self):
        docs = [{"agencies": ["EPA"]}, {"agencies": ["DOD"]}]
        assert _filter_va_docs(docs) == []


# ---------------------------------------------------------------------------
# _shape_fr_document
# ---------------------------------------------------------------------------


class TestShapeFrDocument:
    def test_extracts_fields(self):
        entry = {
            "document_number": "2024-12345",
            "title": "  VA Benefits Rule  ",
            "type": "Rule",
            "agencies": [{"name": "Department of Veterans Affairs"}],
            "publication_date": "2024-06-15",
            "comments_close_on": None,
            "effective_on": "2024-07-15",
            "html_url": "https://fr.gov/doc",
            "comment_url": None,
            "significant": True,
            "abstract": "  An important rule.  ",
        }
        today = date(2024, 6, 15)
        result = _shape_fr_document(entry, today)
        assert result["document_number"] == "2024-12345"
        assert result["title"] == "VA Benefits Rule"
        assert result["abstract"] == "An important rule."
        assert result["agencies"] == ["Department of Veterans Affairs"]
        assert result["significant"] is True

    def test_missing_agencies(self):
        entry = {"agencies": None}
        result = _shape_fr_document(entry, date.today())
        assert result["agencies"] == []


# ---------------------------------------------------------------------------
# _format_highlights
# ---------------------------------------------------------------------------


class TestFormatHighlights:
    def test_empty_documents(self):
        assert _format_highlights([]) == []

    def test_creates_highlights(self):
        docs = [
            {
                "document_number": "2024-001",
                "title": "Test Rule",
                "agencies": ["VA"],
                "comments_close_on": "2024-07-01",
                "effective_on": None,
                "urgency": {"is_urgent": False},
            }
        ]
        result = _format_highlights(docs)
        assert len(result) == 1
        assert "2024-001" in result[0]
        assert "Test Rule" in result[0]

    def test_urgent_docs_prioritized(self):
        docs = [
            {
                "document_number": "NORMAL",
                "title": "Normal",
                "agencies": [],
                "comments_close_on": None,
                "effective_on": None,
                "urgency": {"is_urgent": False},
            },
            {
                "document_number": "URGENT",
                "title": "Urgent",
                "agencies": [],
                "comments_close_on": "2024-06-20",
                "effective_on": None,
                "urgency": {"is_urgent": True},
            },
        ]
        result = _format_highlights(docs)
        assert "URGENT" in result[0]


# ---------------------------------------------------------------------------
# _escape_csv_field
# ---------------------------------------------------------------------------


class TestEscapeCsvField:
    def test_none_returns_empty(self):
        assert _escape_csv_field(None) == ""

    def test_plain_string(self):
        assert _escape_csv_field("hello") == "hello"

    def test_comma_quoted(self):
        result = _escape_csv_field("has,comma")
        assert result.startswith('"')
        assert result.endswith('"')

    def test_quote_double_escaped(self):
        result = _escape_csv_field('has"quote')
        assert '""' in result

    def test_newline_quoted(self):
        result = _escape_csv_field("line1\nline2")
        assert result.startswith('"')

    def test_integer_input(self):
        assert _escape_csv_field(42) == "42"


# ---------------------------------------------------------------------------
# generate_report (mocked)
# ---------------------------------------------------------------------------


class TestGenerateReport:
    @patch("src.reports._enrich_new_documents")
    @patch("src.reports._fetch_new_fr_docs_in_period")
    @patch("src.reports._fetch_runs_in_period")
    def test_daily_report(self, mock_runs, mock_docs, mock_enrich):
        mock_runs.return_value = [
            {
                "id": 1,
                "source_id": "fr",
                "started_at": "2024-01-15T00:00:00",
                "ended_at": "2024-01-15T00:05:00",
                "status": "SUCCESS",
                "records_fetched": 5,
                "errors": [],
            }
        ]
        mock_docs.return_value = [
            {
                "doc_id": "FR-001",
                "published_date": "2024-01-15",
                "first_seen_at": "2024-01-15T10:00:00",
                "source_url": "https://fr.gov",
            }
        ]
        mock_enrich.return_value = [
            {
                "doc_id": "FR-001",
                "document_count": 1,
                "urgent_count": 0,
                "veterans_affairs_documents": 0,
                "fetch_error": None,
                "documents": [],
            }
        ]
        report = generate_report("daily")
        assert report["report_type"] == "daily"
        assert "period" in report
        assert report["summary"]["total_runs"] == 1
        assert report["summary"]["successful_runs"] == 1

    @patch("src.reports._enrich_new_documents")
    @patch("src.reports._fetch_new_fr_docs_in_period")
    @patch("src.reports._fetch_runs_in_period")
    def test_weekly_report(self, mock_runs, mock_docs, mock_enrich):
        mock_runs.return_value = []
        mock_docs.return_value = []
        mock_enrich.return_value = []
        report = generate_report("weekly")
        assert report["report_type"] == "weekly"
        assert report["summary"]["total_runs"] == 0


# ---------------------------------------------------------------------------
# export_json
# ---------------------------------------------------------------------------


class TestExportJson:
    def test_writes_valid_json(self, tmp_path):
        report = {"report_type": "daily", "summary": {"total_runs": 1}}
        filepath = str(tmp_path / "test_report.json")
        result_path = export_json(report, filepath)
        assert Path(result_path).exists()
        with open(result_path) as f:
            data = json.load(f)
        assert data["report_type"] == "daily"

    def test_creates_parent_dirs(self, tmp_path):
        filepath = str(tmp_path / "nested" / "dir" / "report.json")
        export_json({"test": True}, filepath)
        assert Path(filepath).exists()


# ---------------------------------------------------------------------------
# export_csv
# ---------------------------------------------------------------------------


class TestExportCsv:
    def test_writes_csv_files(self, tmp_path):
        report = {
            "runs": [
                {
                    "id": 1,
                    "source_id": "fr",
                    "started_at": "2024-01-15T00:00:00",
                    "ended_at": "2024-01-15T00:05:00",
                    "status": "SUCCESS",
                    "records_fetched": 5,
                    "errors": [],
                }
            ],
            "new_documents": [
                {
                    "doc_id": "FR-001",
                    "published_date": "2024-01-15",
                    "first_seen_at": "2024-01-15T10:00:00",
                    "source_url": "https://fr.gov",
                }
            ],
        }
        base = str(tmp_path / "test_export")
        export_csv(report, base)
        runs_path = tmp_path / "test_export_runs.csv"
        docs_path = tmp_path / "test_export_docs.csv"
        assert runs_path.exists()
        assert docs_path.exists()
        # Verify runs CSV has header + 1 row
        lines = runs_path.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_handles_empty_report(self, tmp_path):
        report = {"runs": [], "new_documents": []}
        base = str(tmp_path / "empty_export")
        export_csv(report, base)
        runs_path = tmp_path / "empty_export_runs.csv"
        assert runs_path.exists()
        lines = runs_path.read_text().strip().split("\n")
        assert len(lines) == 1  # Header only

    def test_enriched_docs_csv(self, tmp_path):
        report = {
            "runs": [],
            "new_documents": [],
            "new_documents_enriched": [
                {
                    "doc_id": "FR-001",
                    "published_date": "2024-01-15",
                    "first_seen_at": "2024-01-15T10:00:00",
                    "source_url": "https://fr.gov",
                    "documents": [
                        {
                            "document_number": "2024-12345",
                            "title": "Test Rule",
                            "type": "Rule",
                            "agencies": ["VA"],
                            "comments_close_on": None,
                            "effective_on": None,
                            "urgency": {"is_urgent": False, "reasons": []},
                            "html_url": "https://fr.gov/doc",
                        }
                    ],
                }
            ],
        }
        base = str(tmp_path / "enriched")
        export_csv(report, base)
        detailed_path = tmp_path / "enriched_docs_detailed.csv"
        assert detailed_path.exists()


# ---------------------------------------------------------------------------
# _build_report_highlights
# ---------------------------------------------------------------------------


class TestBuildReportHighlights:
    def test_empty_returns_empty(self):
        assert _build_report_highlights([]) == []

    def test_creates_highlights_from_docs(self):
        enriched = [
            {
                "doc_id": "FR-001",
                "documents": [
                    {
                        "title": "VA Rule",
                        "agencies": ["VA"],
                        "publication_date": "2024-06-15",
                        "urgency": {"is_urgent": False, "reasons": []},
                        "comments_close_on": None,
                        "effective_on": None,
                    }
                ],
                "documents_scope": "all_documents",
            }
        ]
        result = _build_report_highlights(enriched)
        assert len(result) >= 1
        assert "FR-001" in result[0]
