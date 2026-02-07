"""Tests for src/evidence/api.py — evidence pack API."""

from src.evidence.api import (
    get_citations_for_topic,
    get_evidence_pack,
    list_evidence_packs,
    register_source,
    validate_claim,
)
from src.evidence.generator import EvidencePackGenerator
from src.evidence.models import SourceType

# ── Helpers ──────────────────────────────────────────────────────────────────


def _save_test_pack(tmp_path, populated_db):
    """Save a valid evidence pack and return its pack_id."""
    gen = EvidencePackGenerator(output_dir=tmp_path)
    pack = gen.create_pack("API Test Pack", issue_id="API-1")
    source = gen.add_source_by_id(pack, SourceType.FEDERAL_REGISTER, "2024-01234")
    gen.add_claim(pack, "API test claim", [source.source_id])
    gen.save_pack(pack, validate=True)
    return pack.pack_id


# ── get_evidence_pack ────────────────────────────────────────────────────────


class TestGetEvidencePack:
    def test_retrieves_saved_pack(self, populated_db, tmp_path):
        pack_id = _save_test_pack(tmp_path, populated_db)
        result = get_evidence_pack(pack_id)
        assert result is not None
        assert result.pack_id == pack_id

    def test_nonexistent_pack_returns_none(self, populated_db):
        assert get_evidence_pack("EP-NONEXISTENT-000") is None


# ── list_evidence_packs ─────────────────────────────────────────────────────


class TestListEvidencePacks:
    def test_lists_saved_packs(self, populated_db, tmp_path):
        _save_test_pack(tmp_path, populated_db)
        packs = list_evidence_packs()
        assert len(packs) >= 1

    def test_filter_by_issue_id(self, populated_db, tmp_path):
        _save_test_pack(tmp_path, populated_db)
        packs = list_evidence_packs(issue_id="API-1")
        assert all(p["issue_id"] == "API-1" for p in packs)

    def test_filter_by_status(self, populated_db, tmp_path):
        _save_test_pack(tmp_path, populated_db)
        packs = list_evidence_packs(status="published")
        assert all(p["status"] == "published" for p in packs)

    def test_empty_db_returns_empty(self, use_test_db):
        packs = list_evidence_packs()
        assert packs == []


# ── get_citations_for_topic ──────────────────────────────────────────────────


class TestGetCitationsForTopic:
    def test_finds_citations_for_veteran(self, populated_db):
        results = get_citations_for_topic("veteran")
        assert len(results) > 0
        assert "citation_string" in results[0]

    def test_unknown_topic_returns_empty(self, populated_db):
        results = get_citations_for_topic("xyz_notfound_topic")
        assert results == []


# ── validate_claim ───────────────────────────────────────────────────────────


class TestValidateClaim:
    def test_valid_with_registered_source(self, populated_db, tmp_path):
        # Register a source first so it exists in evidence_sources table
        source_id = register_source(
            source_type="federal_register",
            title="Test Source",
            url="https://example.com",
            date_accessed="2026-02-07",
        )
        is_valid, errors = validate_claim("Test claim", [source_id])
        assert is_valid is True
        assert errors == []

    def test_invalid_without_sources(self, populated_db):
        is_valid, errors = validate_claim("No sources claim", [])
        assert is_valid is False
        assert len(errors) > 0


# ── register_source ─────────────────────────────────────────────────────────


class TestRegisterSource:
    def test_returns_deterministic_id(self, populated_db):
        sid1 = register_source(
            source_type="federal_register",
            title="Test",
            url="https://example.com/1",
            date_accessed="2026-02-07",
            fr_doc_number="2099-99999",
        )
        sid2 = register_source(
            source_type="federal_register",
            title="Test",
            url="https://example.com/1",
            date_accessed="2026-02-07",
            fr_doc_number="2099-99999",
        )
        assert sid1 == sid2

    def test_source_retrievable(self, populated_db):
        from src.evidence.api import get_source_by_id

        sid = register_source(
            source_type="bill",
            title="Registered Bill",
            url="https://example.com/bill",
            date_accessed="2026-02-07",
            bill_number="HR999",
        )
        result = get_source_by_id(sid)
        assert result is not None
        assert result["title"] == "Registered Bill"
