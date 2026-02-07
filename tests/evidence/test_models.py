"""Tests for src/evidence/models.py."""

from src.evidence.models import (
    ClaimType,
    Confidence,
    EvidenceClaim,
    EvidenceExcerpt,
    EvidencePack,
    EvidenceSource,
    PackStatus,
    SourceType,
)

# --- SourceType / ClaimType / Confidence / PackStatus enums ---


class TestEnums:
    def test_source_type_values(self):
        assert SourceType.FEDERAL_REGISTER == "federal_register"
        assert SourceType.BILL == "bill"
        assert SourceType.NEWS == "news"
        assert len(SourceType) == 10

    def test_claim_type_values(self):
        assert ClaimType.OBSERVED == "observed"
        assert ClaimType.INFERRED == "inferred"
        assert ClaimType.MODELED == "modeled"

    def test_confidence_values(self):
        assert Confidence.HIGH == "high"
        assert Confidence.MEDIUM == "medium"
        assert Confidence.LOW == "low"

    def test_pack_status_values(self):
        assert PackStatus.DRAFT == "draft"
        assert PackStatus.VALIDATED == "validated"
        assert PackStatus.PUBLISHED == "published"
        assert PackStatus.FAILED == "failed"


# --- EvidenceExcerpt ---


class TestEvidenceExcerpt:
    def test_citation_with_section_and_page(self, sample_excerpt):
        result = sample_excerpt.to_citation_string()
        assert "Section 3(a)(1)" in result
        assert "p. 42" in result
        assert sample_excerpt.excerpt_text in result

    def test_citation_without_section_reference(self):
        excerpt = EvidenceExcerpt(
            excerpt_text="Some text",
            source_id="abc",
            page_or_line="10",
        )
        result = excerpt.to_citation_string()
        assert "p. 10" in result
        assert "Section" not in result

    def test_citation_long_text_truncated(self):
        long_text = "A" * 150
        excerpt = EvidenceExcerpt(excerpt_text=long_text, source_id="abc")
        result = excerpt.to_citation_string()
        assert "..." in result
        # Only first 100 chars should appear before the ellipsis
        assert long_text[:100] in result
        assert long_text[:101] not in result


# --- EvidenceSource ---


class TestEvidenceSource:
    def test_generate_source_id_deterministic(self):
        id1 = EvidenceSource.generate_source_id(SourceType.FEDERAL_REGISTER, "2024-01234")
        id2 = EvidenceSource.generate_source_id(SourceType.FEDERAL_REGISTER, "2024-01234")
        assert id1 == id2
        assert len(id1) == 16

    def test_generate_source_id_different_inputs(self):
        id1 = EvidenceSource.generate_source_id(SourceType.FEDERAL_REGISTER, "2024-01234")
        id2 = EvidenceSource.generate_source_id(SourceType.BILL, "2024-01234")
        assert id1 != id2

    def test_citation_string_with_fr_citation(self, sample_source):
        result = sample_source.to_citation_string()
        assert "FR Doc. 2024-01234" in result
        assert sample_source.title in result
        assert sample_source.url in result

    def test_citation_string_with_bill_number(self, sample_bill_source):
        result = sample_bill_source.to_citation_string()
        assert "HR100" in result
        assert "118th Congress" in result

    def test_citation_string_with_report_number(self):
        source = EvidenceSource(
            source_id="test",
            source_type=SourceType.GAO_REPORT,
            title="GAO Report",
            url="https://gao.gov/report",
            date_accessed="2026-01-01",
            report_number="GAO-26-100",
        )
        result = source.to_citation_string()
        assert "GAO-26-100" in result

    def test_citation_string_includes_date(self, sample_source):
        result = sample_source.to_citation_string()
        assert "(2026-01-15)" in result

    def test_markdown_citation_footnote_format(self, sample_source):
        result = sample_source.to_markdown_citation(1)
        assert result.startswith("[^1]:")
        assert sample_source.title in result
        assert sample_source.fr_citation in result
        assert f"<{sample_source.url}>" in result


# --- EvidenceClaim ---


class TestEvidenceClaim:
    def test_is_valid_with_sources(self, sample_claim):
        valid, errors = sample_claim.is_valid()
        assert valid is True
        assert errors == []

    def test_is_valid_no_sources(self):
        claim = EvidenceClaim(claim_text="Unsupported claim", source_ids=[])
        valid, errors = claim.is_valid()
        assert valid is False
        assert len(errors) > 0
        assert any("no supporting sources" in e.lower() for e in errors)


# --- EvidencePack ---


class TestEvidencePack:
    def test_generate_pack_id_with_issue(self):
        pack_id = EvidencePack.generate_pack_id("ISSUE-42")
        assert pack_id.startswith("EP-ISSUE-42-")
        assert len(pack_id) > len("EP-ISSUE-42-")

    def test_generate_pack_id_without_issue(self):
        pack_id = EvidencePack.generate_pack_id(None)
        assert pack_id.startswith("EP-")
        assert pack_id.count("-") == 1  # EP-{timestamp}

    def test_add_source_and_get_source(self, sample_pack, sample_source):
        retrieved = sample_pack.get_source(sample_source.source_id)
        assert retrieved is not None
        assert retrieved.title == sample_source.title

    def test_get_source_missing(self, sample_pack):
        assert sample_pack.get_source("nonexistent") is None

    def test_add_claim(self, sample_pack):
        assert len(sample_pack.claims) == 1
        new_claim = EvidenceClaim(claim_text="Second claim", source_ids=["x"])
        sample_pack.add_claim(new_claim)
        assert len(sample_pack.claims) == 2

    def test_validate_valid_pack(self, sample_pack):
        is_valid, errors = sample_pack.validate()
        assert is_valid is True
        assert errors == []
        assert sample_pack.status == PackStatus.VALIDATED

    def test_validate_invalid_claim_references(self, sample_pack):
        bad_claim = EvidenceClaim(claim_text="Bad ref", source_ids=["nonexistent"])
        sample_pack.add_claim(bad_claim)
        is_valid, errors = sample_pack.validate()
        assert is_valid is False
        assert sample_pack.status == PackStatus.FAILED

    def test_to_markdown_includes_key_sections(self, sample_pack):
        md = sample_pack.to_markdown()
        assert "# Evidence Pack: Test Evidence Pack" in md
        assert "EP-TEST-20260207120000" in md
        assert "## Claims" in md
        assert "## Sources" in md
        assert "## Summary" in md
        assert "Test summary" in md
        assert "[^1]" in md

    def test_to_dict_from_dict_roundtrip(self, sample_pack):
        data = sample_pack.to_dict()
        restored = EvidencePack.from_dict(data)
        assert restored.pack_id == sample_pack.pack_id
        assert restored.title == sample_pack.title
        assert restored.issue_id == sample_pack.issue_id
        assert restored.summary == sample_pack.summary
        assert len(restored.claims) == len(sample_pack.claims)
        assert len(restored.sources) == len(sample_pack.sources)
        assert restored.claims[0].claim_text == sample_pack.claims[0].claim_text
        assert restored.status == sample_pack.status
