"""Tests for LDA.gov Lobbying Disclosure integration."""

import json
from unittest.mock import patch

import pytest

from src.db import get_lda_stats, init_db, insert_lda_alert, upsert_lda_filing
from src.fetch_lda import (
    _normalize_filing,
    evaluate_alerts,
)

# ── Sample API responses ──────────────────────────────────────


def _make_raw_filing(**overrides):
    """Build a minimal raw LDA.gov API response filing."""
    base = {
        "filing_uuid": "test-uuid-001",
        "filing_type": "Q1",
        "filing_year": 2026,
        "filing_period": "Q1",
        "dt_posted": "2026-01-15T10:00:00",
        "registrant": {"id": 100, "name": "ACME Lobbying Group"},
        "client": {"id": 200, "name": "Veterans Support Corp"},
        "income": 50000.0,
        "expenses": None,
        "lobbying_activities": [
            {
                "general_issue_code": "VET",
                "description": "Lobbying on veterans benefits issues",
                "government_entities": [{"name": "Department of Veterans Affairs"}],
                "lobbyists": [
                    {
                        "first_name": "John",
                        "last_name": "Smith",
                        "covered_official_position": "",
                    }
                ],
            }
        ],
        "foreign_entities": [],
    }
    base.update(overrides)
    return base


def _make_raw_filing_foreign():
    """Build a filing with foreign entity."""
    return _make_raw_filing(
        filing_uuid="test-uuid-foreign",
        foreign_entities=[{"name": "Foreign Corp", "country": "China", "contribution": 100000}],
    )


def _make_raw_filing_revolving_door():
    """Build a filing with former VA official."""
    return _make_raw_filing(
        filing_uuid="test-uuid-revolving",
        lobbying_activities=[
            {
                "general_issue_code": "VET",
                "description": "Veterans health policy",
                "government_entities": [{"name": "Department of Veterans Affairs"}],
                "lobbyists": [
                    {
                        "first_name": "Jane",
                        "last_name": "Doe",
                        "covered_official_position": "Deputy Secretary, Veterans Affairs",
                    }
                ],
            }
        ],
    )


def _make_raw_filing_registration():
    """Build a new registration filing."""
    return _make_raw_filing(
        filing_uuid="test-uuid-reg",
        filing_type="RR",
    )


# ── Normalization tests ───────────────────────────────────────


class TestNormalizeFiling:
    def test_basic_normalization(self):
        raw = _make_raw_filing()
        result = _normalize_filing(raw)

        assert result["filing_uuid"] == "test-uuid-001"
        assert result["filing_type"] == "Q1"
        assert result["registrant_name"] == "ACME Lobbying Group"
        assert result["client_name"] == "Veterans Support Corp"
        assert result["income_amount"] == 50000.0
        assert result["source_url"] == "https://lda.gov/filings/test-uuid-001/"
        assert result["first_seen_at"] is not None

    def test_extracts_issue_codes(self):
        raw = _make_raw_filing()
        result = _normalize_filing(raw)

        issues = json.loads(result["lobbying_issues_json"])
        assert "VET" in issues

    def test_extracts_govt_entities(self):
        raw = _make_raw_filing()
        result = _normalize_filing(raw)

        entities = json.loads(result["govt_entities_json"])
        assert "Department of Veterans Affairs" in entities

    def test_extracts_lobbyists(self):
        raw = _make_raw_filing()
        result = _normalize_filing(raw)

        lobbyists = json.loads(result["lobbyists_json"])
        assert len(lobbyists) == 1
        assert lobbyists[0]["name"] == "John Smith"

    def test_foreign_entity_detection(self):
        raw = _make_raw_filing_foreign()
        result = _normalize_filing(raw)

        assert result["foreign_entity_listed"] == 1
        foreign = json.loads(result["foreign_entities_json"])
        assert len(foreign) == 1

    def test_covered_positions_extraction(self):
        raw = _make_raw_filing_revolving_door()
        result = _normalize_filing(raw)

        positions = json.loads(result["covered_positions_json"])
        assert len(positions) == 1
        assert "Veterans Affairs" in positions[0]["covered_position"]

    def test_missing_fields_handled(self):
        """Minimal filing with missing optional fields."""
        raw = {
            "filing_uuid": "test-uuid-minimal",
            "filing_type": "Q1",
            "dt_posted": "2026-01-01",
            "registrant": {"name": "Test Firm"},
            "client": {"name": "Test Client"},
            "lobbying_activities": [],
            "foreign_entities": [],
        }
        result = _normalize_filing(raw)
        assert result["filing_uuid"] == "test-uuid-minimal"
        assert result["lobbying_issues_json"] is None
        assert result["foreign_entity_listed"] == 0


# ── VA Relevance scoring tests ────────────────────────────────


class TestVARelevance:
    def test_critical_foreign_entity(self):
        raw = _make_raw_filing_foreign()
        result = _normalize_filing(raw)
        assert result["va_relevance_score"] == "CRITICAL"
        assert "foreign_entity" in result["va_relevance_reason"]

    def test_critical_revolving_door(self):
        raw = _make_raw_filing_revolving_door()
        result = _normalize_filing(raw)
        assert result["va_relevance_score"] == "CRITICAL"
        assert "revolving_door" in result["va_relevance_reason"]

    def test_high_va_entity_targeted(self):
        raw = _make_raw_filing()
        result = _normalize_filing(raw)
        # Has VET issue code + VA entity = at least HIGH
        assert result["va_relevance_score"] in ("HIGH", "CRITICAL")

    def test_high_new_registration(self):
        raw = _make_raw_filing_registration()
        result = _normalize_filing(raw)
        assert result["va_relevance_score"] in ("HIGH", "CRITICAL")

    def test_medium_vet_issue_code(self):
        """Filing with VET issue code but no direct VA entity."""
        raw = _make_raw_filing(
            filing_uuid="test-uuid-medium",
            lobbying_activities=[
                {
                    "general_issue_code": "VET",
                    "description": "Veterans benefits",
                    "government_entities": [
                        {"name": "Department of Defense"}  # Not VA
                    ],
                    "lobbyists": [],
                }
            ],
        )
        result = _normalize_filing(raw)
        assert result["va_relevance_score"] in ("MEDIUM", "HIGH")

    def test_low_tangential(self):
        """Filing with no VA indicators."""
        raw = _make_raw_filing(
            filing_uuid="test-uuid-low",
            lobbying_activities=[
                {
                    "general_issue_code": "TAX",
                    "description": "Tax policy reform",
                    "government_entities": [{"name": "Department of Treasury"}],
                    "lobbyists": [],
                }
            ],
        )
        result = _normalize_filing(raw)
        assert result["va_relevance_score"] == "LOW"


# ── Alert evaluation tests ────────────────────────────────────


class TestAlertEvaluation:
    def test_new_registration_alert(self):
        raw = _make_raw_filing_registration()
        filing = _normalize_filing(raw)
        alerts = evaluate_alerts(filing)

        reg_alerts = [a for a in alerts if a["alert_type"] == "new_registration"]
        assert len(reg_alerts) == 1
        assert reg_alerts[0]["severity"] == "HIGH"

    def test_foreign_entity_alert(self):
        raw = _make_raw_filing_foreign()
        filing = _normalize_filing(raw)
        alerts = evaluate_alerts(filing)

        foreign_alerts = [a for a in alerts if a["alert_type"] == "foreign_entity"]
        assert len(foreign_alerts) == 1
        assert foreign_alerts[0]["severity"] == "HIGH"

    def test_revolving_door_alert(self):
        raw = _make_raw_filing_revolving_door()
        filing = _normalize_filing(raw)
        alerts = evaluate_alerts(filing)

        door_alerts = [a for a in alerts if a["alert_type"] == "revolving_door"]
        assert len(door_alerts) == 1
        assert "Former VA official" in door_alerts[0]["summary"]

    def test_amendment_alert(self):
        raw = _make_raw_filing(
            filing_uuid="test-uuid-amend",
            filing_type="RA",
        )
        filing = _normalize_filing(raw)
        alerts = evaluate_alerts(filing)

        amend_alerts = [a for a in alerts if a["alert_type"] == "amendment"]
        assert len(amend_alerts) == 1
        assert amend_alerts[0]["severity"] == "MEDIUM"

    def test_low_relevance_no_alerts(self):
        """Low relevance filings should produce no alerts."""
        raw = _make_raw_filing(
            filing_uuid="test-uuid-no-alert",
            filing_type="Q1",
            lobbying_activities=[
                {
                    "general_issue_code": "TAX",
                    "description": "Tax reform",
                    "government_entities": [{"name": "Treasury"}],
                    "lobbyists": [],
                }
            ],
        )
        filing = _normalize_filing(raw)
        alerts = evaluate_alerts(filing)
        assert len(alerts) == 0


# ── DB round-trip tests ───────────────────────────────────────


class TestLDADB:
    @pytest.fixture(autouse=True)
    def setup_db(self):
        init_db()

    def test_upsert_new_filing(self):
        raw = _make_raw_filing(filing_uuid="db-test-001")
        filing = _normalize_filing(raw)

        is_new = upsert_lda_filing(filing)
        assert is_new is True

    def test_upsert_duplicate_filing(self):
        raw = _make_raw_filing(filing_uuid="db-test-dup")
        filing = _normalize_filing(raw)

        first = upsert_lda_filing(filing)
        second = upsert_lda_filing(filing)

        assert first is True
        assert second is False

    def test_insert_alert(self):
        raw = _make_raw_filing(filing_uuid="db-test-alert")
        filing = _normalize_filing(raw)
        upsert_lda_filing(filing)

        alert = {
            "filing_uuid": "db-test-alert",
            "alert_type": "new_registration",
            "severity": "HIGH",
            "summary": "Test alert",
            "details_json": "{}",
            "created_at": "2026-01-15T10:00:00Z",
        }
        alert_id = insert_lda_alert(alert)
        assert alert_id is not None
        assert alert_id > 0

    def test_get_stats(self):
        raw = _make_raw_filing(filing_uuid="db-test-stats")
        filing = _normalize_filing(raw)
        upsert_lda_filing(filing)

        stats = get_lda_stats()
        assert stats["total_filings"] >= 1
        assert isinstance(stats["by_type"], dict)
        assert isinstance(stats["by_relevance"], dict)


# ── Runner tests (mocked API) ────────────────────────────────


class TestRunLDADaily:
    @patch("src.run_lda.fetch_filings_since")
    @patch("src.run_lda.send_new_docs_alert")
    @patch("src.run_lda.send_error_alert")
    def test_daily_no_data(self, mock_error, mock_docs, mock_fetch):
        mock_fetch.return_value = []
        init_db()

        from src.run_lda import run_lda_daily

        result = run_lda_daily(since="2026-01-15", dry_run=True)

        assert result["status"] == "NO_DATA"
        mock_error.assert_not_called()
        mock_docs.assert_not_called()

    @patch("src.run_lda.fetch_filings_since")
    @patch("src.run_lda.send_new_docs_alert")
    @patch("src.run_lda.send_error_alert")
    def test_daily_success_dry_run(self, mock_error, mock_docs, mock_fetch):
        raw = _make_raw_filing(filing_uuid="run-test-001")
        filing = _normalize_filing(raw)
        mock_fetch.return_value = [filing]
        init_db()

        from src.run_lda import run_lda_daily

        result = run_lda_daily(since="2026-01-15", dry_run=True)

        # Dry run doesn't write to DB so status depends on filings found
        assert result["status"] in ("SUCCESS", "NO_DATA")
        assert result["records_fetched"] == 1

    @patch("src.run_lda.fetch_filings_since")
    @patch("src.run_lda.send_new_docs_alert")
    @patch("src.run_lda.send_error_alert")
    def test_daily_success_live(self, mock_error, mock_docs, mock_fetch):
        raw = _make_raw_filing(filing_uuid="run-test-live-001")
        filing = _normalize_filing(raw)
        mock_fetch.return_value = [filing]
        init_db()

        from src.run_lda import run_lda_daily

        result = run_lda_daily(since="2026-01-15", dry_run=False)

        assert result["status"] == "SUCCESS"
        assert result["records_fetched"] == 1
