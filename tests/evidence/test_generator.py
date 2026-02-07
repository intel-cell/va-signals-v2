"""Tests for src/evidence/generator.py — evidence pack generation."""

import pytest

from src.evidence.generator import (
    EvidencePackGenerator,
    generate_quick_evidence_pack,
)
from src.evidence.models import (
    PackStatus,
    SourceType,
)
from src.evidence.validator import ValidationError


class TestEvidencePackGeneratorCreatePack:
    def test_create_pack_returns_draft(self):
        gen = EvidencePackGenerator()
        pack = gen.create_pack("Test Pack", issue_id="ISS-1", summary="test")
        assert pack.status == PackStatus.DRAFT

    def test_create_pack_has_title(self):
        gen = EvidencePackGenerator()
        pack = gen.create_pack("My Title")
        assert pack.title == "My Title"

    def test_create_pack_has_issue_id(self):
        gen = EvidencePackGenerator()
        pack = gen.create_pack("Title", issue_id="ISS-1")
        assert pack.issue_id == "ISS-1"

    def test_create_pack_id_contains_issue(self):
        gen = EvidencePackGenerator()
        pack = gen.create_pack("Title", issue_id="ISS-1")
        assert "ISS-1" in pack.pack_id


class TestAddSourceById:
    def test_adds_fr_source(self, populated_db):
        gen = EvidencePackGenerator()
        pack = gen.create_pack("Test")
        source = gen.add_source_by_id(pack, SourceType.FEDERAL_REGISTER, "2024-01234")
        assert source is not None
        assert source.source_id in pack.sources

    def test_adds_bill_source(self, populated_db):
        gen = EvidencePackGenerator()
        pack = gen.create_pack("Test")
        source = gen.add_source_by_id(pack, SourceType.BILL, "hr-118-100")
        assert source is not None
        assert source.source_id in pack.sources

    def test_nonexistent_returns_none_pack_unchanged(self, populated_db):
        gen = EvidencePackGenerator()
        pack = gen.create_pack("Test")
        result = gen.add_source_by_id(pack, SourceType.FEDERAL_REGISTER, "no-such-doc")
        assert result is None
        assert len(pack.sources) == 0


class TestAddClaim:
    def test_claim_added_to_pack(self, populated_db):
        gen = EvidencePackGenerator()
        pack = gen.create_pack("Test")
        source = gen.add_source_by_id(pack, SourceType.FEDERAL_REGISTER, "2024-01234")
        claim = gen.add_claim(pack, "Test claim", [source.source_id])
        assert len(pack.claims) == 1
        assert claim.last_verified is not None


class TestAutoPopulateSources:
    def test_finds_sources_for_keyword(self, populated_db):
        gen = EvidencePackGenerator()
        pack = gen.create_pack("Test")
        added = gen.auto_populate_sources(pack, keywords=["veteran"])
        assert len(added) > 0
        assert len(pack.sources) > 0


class TestSavePack:
    def test_saves_file_and_db(self, populated_db, tmp_path):
        gen = EvidencePackGenerator(output_dir=tmp_path)
        pack = gen.create_pack("Save Test", issue_id="SAVE-1")
        source = gen.add_source_by_id(pack, SourceType.FEDERAL_REGISTER, "2024-01234")
        gen.add_claim(pack, "Saving claim", [source.source_id])
        path = gen.save_pack(pack, validate=True)
        assert path.exists()
        assert pack.status == PackStatus.PUBLISHED

    def test_save_invalid_pack_raises(self, populated_db, tmp_path):
        gen = EvidencePackGenerator(output_dir=tmp_path)
        pack = gen.create_pack("Bad Pack")
        # No sources, no claims -> validation should fail
        with pytest.raises(ValidationError):
            gen.save_pack(pack, validate=True)


class TestGenerateQuickEvidencePack:
    def test_generates_file(self, populated_db, tmp_path):
        path = generate_quick_evidence_pack(
            topic="Veterans Health",
            keywords=["veteran"],
            output_dir=tmp_path,
        )
        assert path.exists()
