"""Tests for oversight data fixes: ml_score INSERT and theme extraction."""

import pytest

from src.oversight.db_helpers import insert_om_event, get_om_event
from src.oversight.runner import _extract_theme


class TestInsertMlScoreFields:
    """Verify insert_om_event stores ml_score and ml_risk_level."""

    def test_insert_with_ml_score(self):
        event = {
            "event_id": "test-ml-001",
            "event_type": "report_release",
            "primary_source_type": "gao",
            "primary_url": "https://gao.gov/ml-test",
            "pub_timestamp": "2026-01-20T10:00:00Z",
            "pub_precision": "datetime",
            "pub_source": "extracted",
            "title": "GAO ML Test Report",
            "ml_score": 0.85,
            "ml_risk_level": "high",
            "fetched_at": "2026-01-20T12:00:00Z",
        }

        insert_om_event(event)
        result = get_om_event("test-ml-001")

        assert result is not None
        assert result["event_id"] == "test-ml-001"

        # Verify ml fields are stored by querying directly
        from src.db import connect, execute

        con = connect()
        cur = execute(
            con,
            "SELECT ml_score, ml_risk_level FROM om_events WHERE event_id = :eid",
            {"eid": "test-ml-001"},
        )
        row = cur.fetchone()
        con.close()

        assert row is not None
        assert row[0] == pytest.approx(0.85)
        assert row[1] == "high"

    def test_insert_with_null_ml_score(self):
        event = {
            "event_id": "test-ml-002",
            "event_type": "report_release",
            "primary_source_type": "oig",
            "primary_url": "https://oig.va.gov/ml-null-test",
            "pub_timestamp": "2026-01-20T10:00:00Z",
            "pub_precision": "datetime",
            "pub_source": "extracted",
            "title": "OIG Null ML Test",
            "fetched_at": "2026-01-20T12:00:00Z",
        }

        insert_om_event(event)

        from src.db import connect, execute

        con = connect()
        cur = execute(
            con,
            "SELECT ml_score, ml_risk_level FROM om_events WHERE event_id = :eid",
            {"eid": "test-ml-002"},
        )
        row = cur.fetchone()
        con.close()

        assert row is not None
        assert row[0] is None
        assert row[1] is None


class TestExtractTheme:
    """Verify keyword-based theme extraction and source_type fallback."""

    def test_oversight_report_keywords(self):
        assert _extract_theme("GAO Audit of VA Healthcare", "gao") == "oversight_report"
        assert _extract_theme("Annual Review of Benefits", "oig") == "oversight_report"
        assert _extract_theme("Assessment of Wait Times", "news_wire") == "oversight_report"
        assert _extract_theme("Program Evaluation Results", "gao") == "oversight_report"

    def test_congressional_action_keywords(self):
        assert _extract_theme("Senate Hearing on VA Budget", "committee_press") == "congressional_action"
        assert _extract_theme("Committee Markup Session", "congressional_record") == "congressional_action"
        assert _extract_theme("New Legislation Introduced", "news_wire") == "congressional_action"
        assert _extract_theme("House Bill on Veterans", "committee_press") == "congressional_action"
        assert _extract_theme("Joint Resolution for VA Reform", "congressional_record") == "congressional_action"

    def test_legal_ruling_keywords(self):
        assert _extract_theme("Court Rules on Benefits Case", "cafc") == "legal_ruling"
        assert _extract_theme("Federal Circuit Decision", "cafc") == "legal_ruling"
        assert _extract_theme("Judge Orders VA Compliance", "news_wire") == "legal_ruling"
        assert _extract_theme("Appeal Denied in Smith v. VA", "bva") == "legal_ruling"

    def test_policy_change_keywords(self):
        assert _extract_theme("New VA Policy on Telehealth", "gao") == "policy_change"
        assert _extract_theme("Updated Regulation for Claims", "news_wire") == "policy_change"
        assert _extract_theme("VA Directive on Scheduling", "oig") == "policy_change"

    def test_budget_fiscal_keywords(self):
        assert _extract_theme("VA Budget Request for FY2027", "committee_press") == "budget_fiscal"
        assert _extract_theme("Funding Increase for Mental Health", "news_wire") == "budget_fiscal"
        assert _extract_theme("New Appropriation Approved", "congressional_record") == "budget_fiscal"

    def test_personnel_keywords(self):
        assert _extract_theme("New VA Secretary Nominee", "news_wire") == "personnel"
        assert _extract_theme("Director Resigns Amid Scandal", "investigative") == "personnel"
        assert _extract_theme("Leadership Changes at VA", "trade_press") == "personnel"

    def test_healthcare_operations_keywords(self):
        assert _extract_theme("Hospital Inspection Results", "oig") == "healthcare_operations"
        assert _extract_theme("Wait Time Improvements at VA", "news_wire") == "healthcare_operations"
        assert _extract_theme("Staffing Shortages Continue", "trade_press") == "healthcare_operations"

    def test_benefits_claims_keywords(self):
        assert _extract_theme("Disability Claims Backlog Grows", "news_wire") == "benefits_claims"
        assert _extract_theme("Compensation Rate Changes", "gao") == "benefits_claims"
        assert _extract_theme("Pension Reform Proposed", "committee_press") == "benefits_claims"

    def test_source_type_fallback_gao(self):
        assert _extract_theme("Untitled Document XYZ", "gao") == "oversight_report"

    def test_source_type_fallback_oig(self):
        assert _extract_theme("Untitled Document XYZ", "oig") == "oversight_report"

    def test_source_type_fallback_congressional_record(self):
        assert _extract_theme("Untitled Document XYZ", "congressional_record") == "congressional_action"

    def test_source_type_fallback_committee_press(self):
        assert _extract_theme("Untitled Document XYZ", "committee_press") == "congressional_action"

    def test_source_type_fallback_cafc(self):
        assert _extract_theme("Untitled Document XYZ", "cafc") == "legal_ruling"

    def test_source_type_fallback_bva(self):
        assert _extract_theme("Untitled Document XYZ", "bva") == "legal_ruling"

    def test_no_match_returns_none(self):
        assert _extract_theme("Untitled Document XYZ", "news_wire") is None
        assert _extract_theme("Untitled Document XYZ", "investigative") is None
        assert _extract_theme("Untitled Document XYZ", "trade_press") is None
