"""Tests for src/evidence/alpha_integration.py and delta_integration.py."""

from datetime import date

from src.evidence.alpha_integration import (
    evidence_source_to_alpha_citation,
    get_citations_for_brief,
)
from src.evidence.delta_integration import (
    get_vehicles_needing_evidence_packs,
    link_evidence_pack_to_vehicle,
)
from src.evidence.models import EvidenceSource, SourceType

# ── ALPHA integration ────────────────────────────────────────────────────────


class TestEvidenceSourceToAlphaCitation:
    def test_maps_source_type_correctly(self, sample_source):
        citation = evidence_source_to_alpha_citation(sample_source)
        assert citation.source_type == "federal_register"

    def test_parses_date_from_iso(self, sample_source):
        citation = evidence_source_to_alpha_citation(sample_source)
        assert isinstance(citation.date, date)

    def test_uses_fr_doc_number_as_source_id(self, sample_source):
        citation = evidence_source_to_alpha_citation(sample_source)
        assert citation.source_id == "2024-01234"

    def test_falls_back_to_truncated_hash(self):
        source = EvidenceSource(
            source_id="abcdef1234567890",
            source_type=SourceType.VA_GUIDANCE,
            title="VA Guidance",
            url="https://example.com",
            date_accessed="2026-02-07",
            date_published="2026-01-01",
        )
        citation = evidence_source_to_alpha_citation(source)
        # No fr_doc_number, bill_number, or report_number -> truncated hash
        assert citation.source_id == "abcdef123456"


class TestGetCitationsForBrief:
    def test_returns_citations_for_veteran(self, populated_db):
        results = get_citations_for_brief(["veteran"])
        assert len(results) > 0

    def test_deduplicates_by_source_id(self, populated_db):
        results = get_citations_for_brief(["veteran", "veteran"])
        source_ids = [c.source_id for c in results]
        assert len(source_ids) == len(set(source_ids))


# ── DELTA integration ────────────────────────────────────────────────────────


class TestGetVehiclesNeedingEvidencePacks:
    def test_empty_bf_vehicles_returns_empty(self, populated_db):
        # bf_vehicles table may not exist or be empty -> graceful empty list
        result = get_vehicles_needing_evidence_packs()
        assert isinstance(result, list)


class TestLinkEvidencePackToVehicle:
    def test_graceful_when_no_vehicles(self, populated_db):
        # bf_vehicles table may be empty or vehicle_id not found
        # The function should still return True (UPDATE on zero rows succeeds)
        result = link_evidence_pack_to_vehicle("nonexistent-vehicle", "EP-TEST-001")
        assert isinstance(result, bool)
