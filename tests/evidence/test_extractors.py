"""Tests for src/evidence/extractors.py — citation extractors."""

from src.evidence.extractors import (
    extract_bill_citation,
    extract_fr_citation,
    extract_fr_comment_deadline,
    extract_fr_effective_date,
    extract_hearing_citation,
    extract_oversight_citation,
    search_citations_by_keyword,
)
from src.evidence.models import SourceType

# ── Federal Register extractor ───────────────────────────────────────────────


class TestExtractFrCitation:
    def test_returns_source_for_existing_doc(self, populated_db):
        source = extract_fr_citation("2024-01234")
        assert source is not None

    def test_correct_source_type(self, populated_db):
        source = extract_fr_citation("2024-01234")
        assert source.source_type == SourceType.FEDERAL_REGISTER

    def test_has_fr_doc_number(self, populated_db):
        source = extract_fr_citation("2024-01234")
        assert source.fr_doc_number == "2024-01234"

    def test_has_fr_citation(self, populated_db):
        source = extract_fr_citation("2024-01234")
        assert source.fr_citation == "FR Doc. 2024-01234"

    def test_has_url(self, populated_db):
        source = extract_fr_citation("2024-01234")
        assert source.url == "https://www.federalregister.gov/d/2024-01234"

    def test_has_date_published(self, populated_db):
        source = extract_fr_citation("2024-01234")
        assert source.date_published == "2026-01-15"

    def test_has_summary_metadata(self, populated_db):
        source = extract_fr_citation("2024-01234")
        assert "summary" in source.metadata
        assert source.metadata["summary"] == "Test veteran summary"

    def test_nonexistent_doc_returns_none(self, populated_db):
        assert extract_fr_citation("9999-00000") is None


# ── Bill extractor ───────────────────────────────────────────────────────────


class TestExtractBillCitation:
    def test_returns_source_for_existing_bill(self, populated_db):
        source = extract_bill_citation("hr-118-100")
        assert source is not None

    def test_correct_bill_number(self, populated_db):
        source = extract_bill_citation("hr-118-100")
        assert source.bill_number == "HR100"

    def test_correct_bill_congress(self, populated_db):
        source = extract_bill_citation("hr-118-100")
        assert source.bill_congress == 118

    def test_has_congress_gov_url(self, populated_db):
        source = extract_bill_citation("hr-118-100")
        assert "congress.gov" in source.url

    def test_has_metadata(self, populated_db):
        source = extract_bill_citation("hr-118-100")
        assert source.metadata.get("sponsor_name") == "Smith"
        assert source.metadata.get("policy_area") == "Veterans"

    def test_nonexistent_bill_returns_none(self, populated_db):
        assert extract_bill_citation("hr-999-999") is None


# ── Oversight extractor ──────────────────────────────────────────────────────


class TestExtractOversightCitation:
    def test_returns_source_for_existing_event(self, populated_db):
        source = extract_oversight_citation("gao-test-001")
        assert source is not None

    def test_correct_source_type(self, populated_db):
        source = extract_oversight_citation("gao-test-001")
        assert source.source_type == SourceType.GAO_REPORT

    def test_report_number_from_canonical_refs(self, populated_db):
        source = extract_oversight_citation("gao-test-001")
        assert source.report_number == "GAO-26-100"

    def test_nonexistent_event_returns_none(self, populated_db):
        assert extract_oversight_citation("xyz-000") is None


# ── Hearing extractor ────────────────────────────────────────────────────────


class TestExtractHearingCitation:
    def test_returns_source_for_existing_hearing(self, populated_db):
        source = extract_hearing_citation("hearing-001")
        assert source is not None

    def test_correct_source_type(self, populated_db):
        source = extract_hearing_citation("hearing-001")
        assert source.source_type == SourceType.HEARING

    def test_has_committee_name(self, populated_db):
        source = extract_hearing_citation("hearing-001")
        assert source.metadata.get("committee_name") == "Senate Veterans Affairs"

    def test_nonexistent_hearing_returns_none(self, populated_db):
        assert extract_hearing_citation("hearing-999") is None


# ── Keyword search ───────────────────────────────────────────────────────────


class TestSearchCitationsByKeyword:
    def test_finds_fr_and_oversight_for_veteran(self, populated_db):
        results = search_citations_by_keyword("veteran")
        assert len(results) > 0

    def test_no_results_for_unknown_keyword(self, populated_db):
        results = search_citations_by_keyword("xyz_notfound")
        assert results == []

    def test_source_types_filter(self, populated_db):
        results = search_citations_by_keyword("veteran", source_types=[SourceType.FEDERAL_REGISTER])
        for r in results:
            assert r.source_type == SourceType.FEDERAL_REGISTER


# ── Regex helpers ────────────────────────────────────────────────────────────


class TestFrRegexHelpers:
    def test_effective_date_found(self):
        text = "Effective date: January 15, 2026"
        assert extract_fr_effective_date(text) == "January 15, 2026"

    def test_effective_date_not_found(self):
        assert extract_fr_effective_date("No date here") is None

    def test_comment_deadline_found(self):
        text = "Comments must be received by March 1, 2026"
        assert extract_fr_comment_deadline(text) == "March 1, 2026"

    def test_comment_deadline_not_found(self):
        assert extract_fr_comment_deadline("No deadline") is None
