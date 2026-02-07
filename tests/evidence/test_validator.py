"""Tests for src/evidence/validator.py."""

import pytest

from src.evidence.models import (
    ClaimType,
    Confidence,
    EvidenceClaim,
    EvidencePack,
    EvidenceSource,
    PackStatus,
    SourceType,
)
from src.evidence.validator import (
    ValidationError,
    classify_claim_type,
    require_valid_pack,
    suggest_confidence,
    validate_claim,
    validate_claim_text_has_source,
    validate_pack,
    validate_source,
)

# --- validate_source ---


class TestValidateSource:
    def test_valid_source_passes(self, sample_source):
        result = validate_source(sample_source)
        assert result.passed is True
        assert result.errors == []

    def test_missing_url_error(self, sample_source):
        sample_source.url = ""
        result = validate_source(sample_source)
        assert result.passed is False
        assert any("Missing URL" in e for e in result.errors)

    def test_missing_date_accessed_error(self, sample_source):
        sample_source.date_accessed = ""
        result = validate_source(sample_source)
        assert result.passed is False
        assert any("Missing access date" in e for e in result.errors)

    def test_bad_url_format_error(self, sample_source):
        sample_source.url = "ftp://example.com/file"
        result = validate_source(sample_source)
        assert result.passed is False
        assert any("Invalid URL format" in e for e in result.errors)

    def test_missing_date_published_warning(self):
        source = EvidenceSource(
            source_id="test",
            source_type=SourceType.NEWS,
            title="News Article",
            url="https://example.com",
            date_accessed="2026-01-01",
            date_published=None,
        )
        result = validate_source(source)
        assert result.passed is True
        assert any("Missing publication date" in w for w in result.warnings)

    def test_missing_title_warning(self):
        source = EvidenceSource(
            source_id="test",
            source_type=SourceType.NEWS,
            title="",
            url="https://example.com",
            date_accessed="2026-01-01",
        )
        result = validate_source(source)
        assert result.passed is True
        assert any("Missing title" in w for w in result.warnings)


# --- validate_claim ---


class TestValidateClaim:
    def test_claim_with_sources_passes(self, sample_source, sample_claim):
        sources = {sample_source.source_id: sample_source}
        result = validate_claim(sample_claim, sources, 0)
        assert result.passed is True
        assert result.errors == []

    def test_claim_no_sources_error(self, sample_source):
        claim = EvidenceClaim(claim_text="No sources", source_ids=[])
        sources = {sample_source.source_id: sample_source}
        result = validate_claim(claim, sources, 0)
        assert result.passed is False
        assert any("No supporting sources" in e for e in result.errors)

    def test_claim_unknown_source_error(self, sample_source):
        claim = EvidenceClaim(claim_text="Bad ref", source_ids=["nonexistent"])
        sources = {sample_source.source_id: sample_source}
        result = validate_claim(claim, sources, 0)
        assert result.passed is False
        assert any("unknown source" in e.lower() for e in result.errors)

    def test_modeled_high_confidence_warning(self, sample_source):
        claim = EvidenceClaim(
            claim_text="The model predicts 50% increase",
            claim_type=ClaimType.MODELED,
            confidence=Confidence.HIGH,
            source_ids=[sample_source.source_id],
        )
        sources = {sample_source.source_id: sample_source}
        result = validate_claim(claim, sources, 0)
        assert result.passed is True
        assert any("Modeled claim marked high confidence" in w for w in result.warnings)

    def test_modeled_without_methodology_keywords_warning(self, sample_source):
        claim = EvidenceClaim(
            claim_text="Veterans will receive more benefits",
            claim_type=ClaimType.MODELED,
            confidence=Confidence.MEDIUM,
            source_ids=[sample_source.source_id],
        )
        sources = {sample_source.source_id: sample_source}
        result = validate_claim(claim, sources, 0)
        assert result.passed is True
        assert any("calculation methodology" in w for w in result.warnings)

    def test_inferred_high_confidence_warning(self, sample_source):
        claim = EvidenceClaim(
            claim_text="This suggests VA will expand",
            claim_type=ClaimType.INFERRED,
            confidence=Confidence.HIGH,
            source_ids=[sample_source.source_id],
        )
        sources = {sample_source.source_id: sample_source}
        result = validate_claim(claim, sources, 0)
        assert result.passed is True
        assert any("Inferred claim marked high confidence" in w for w in result.warnings)

    def test_low_confidence_single_source_warning(self, sample_source):
        claim = EvidenceClaim(
            claim_text="Something happened",
            claim_type=ClaimType.OBSERVED,
            confidence=Confidence.LOW,
            source_ids=[sample_source.source_id],
        )
        sources = {sample_source.source_id: sample_source}
        result = validate_claim(claim, sources, 0)
        assert result.passed is True
        assert any("Low confidence with single source" in w for w in result.warnings)

    def test_claim_index_stored_in_result(self, sample_source, sample_claim):
        sources = {sample_source.source_id: sample_source}
        result = validate_claim(sample_claim, sources, 5)
        assert result.claim_index == 5


# --- validate_pack ---


class TestValidatePack:
    def test_valid_pack_passes(self, sample_pack):
        result = validate_pack(sample_pack, strict=False)
        assert result.passed is True
        assert sample_pack.status == PackStatus.VALIDATED

    def test_invalid_source_fails(self, sample_pack):
        # Add a source with bad URL
        bad_source = EvidenceSource(
            source_id="bad",
            source_type=SourceType.NEWS,
            title="Bad",
            url="",
            date_accessed="2026-01-01",
        )
        sample_pack.add_source(bad_source)
        result = validate_pack(sample_pack, strict=False)
        assert result.passed is False
        assert sample_pack.status == PackStatus.FAILED

    def test_invalid_claim_fails(self, sample_pack):
        bad_claim = EvidenceClaim(claim_text="No sources", source_ids=[])
        sample_pack.add_claim(bad_claim)
        result = validate_pack(sample_pack, strict=False)
        assert result.passed is False
        assert sample_pack.status == PackStatus.FAILED

    def test_strict_warnings_become_errors(self, sample_source):
        pack = EvidencePack(
            pack_id="EP-STRICT",
            title="Strict Pack",
            generated_at="2026-01-01",
            generated_by="test",
        )
        # Source without date_published triggers a warning
        source_no_date = EvidenceSource(
            source_id="nodate",
            source_type=SourceType.NEWS,
            title="No date pub",
            url="https://example.com",
            date_accessed="2026-01-01",
            date_published=None,
        )
        pack.add_source(source_no_date)
        claim = EvidenceClaim(
            claim_text="Claim with valid source",
            source_ids=["nodate"],
        )
        pack.add_claim(claim)
        result = validate_pack(pack, strict=True)
        assert result.passed is False
        assert any("[STRICT]" in e for e in result.errors)

    def test_empty_claims_warning(self, sample_source):
        pack = EvidencePack(
            pack_id="EP-EMPTY",
            title="Empty Pack",
            generated_at="2026-01-01",
            generated_by="test",
        )
        pack.add_source(sample_source)
        # No claims added
        result = validate_pack(pack, strict=False)
        assert result.passed is True
        assert any("no claims" in w.lower() for w in result.warnings)

    def test_empty_sources_error(self):
        pack = EvidencePack(
            pack_id="EP-NOSRC",
            title="No Sources",
            generated_at="2026-01-01",
            generated_by="test",
        )
        result = validate_pack(pack, strict=False)
        assert result.passed is False
        assert any("no sources" in e.lower() for e in result.errors)


# --- require_valid_pack ---


class TestRequireValidPack:
    def test_returns_valid_pack(self, sample_pack):
        result = require_valid_pack(sample_pack)
        assert result is sample_pack
        assert sample_pack.status == PackStatus.VALIDATED

    def test_raises_on_invalid_pack(self):
        pack = EvidencePack(
            pack_id="EP-BAD",
            title="Bad Pack",
            generated_at="2026-01-01",
            generated_by="test",
        )
        # No sources -> error
        with pytest.raises(ValidationError) as exc_info:
            require_valid_pack(pack)
        assert len(exc_info.value.errors) > 0


# --- validate_claim_text_has_source ---


class TestValidateClaimTextHasSource:
    def test_valid_returns_true(self, sample_source):
        sources = {sample_source.source_id: sample_source}
        valid, errors = validate_claim_text_has_source(
            "VA published rule", [sample_source.source_id], sources
        )
        assert valid is True
        assert errors == []

    def test_no_sources_returns_false(self, sample_source):
        sources = {sample_source.source_id: sample_source}
        valid, errors = validate_claim_text_has_source("Something", [], sources)
        assert valid is False
        assert any("at least one" in e.lower() for e in errors)

    def test_unknown_source_returns_false(self, sample_source):
        sources = {sample_source.source_id: sample_source}
        valid, errors = validate_claim_text_has_source("Something", ["unknown-id"], sources)
        assert valid is False
        assert any("not found" in e.lower() for e in errors)


# --- classify_claim_type ---


class TestClassifyClaimType:
    def test_estimated_returns_modeled(self):
        assert classify_claim_type("The estimated cost is $5M") == ClaimType.MODELED

    def test_suggests_without_quote_returns_inferred(self):
        assert classify_claim_type("This suggests VA will expand") == ClaimType.INFERRED

    def test_direct_quote_overrides_inference(self):
        result = classify_claim_type("This suggests VA will expand", has_direct_quote=True)
        assert result == ClaimType.OBSERVED

    def test_has_calculation_returns_modeled(self):
        result = classify_claim_type("Neutral statement", has_calculation=True)
        assert result == ClaimType.MODELED

    def test_neutral_text_returns_observed(self):
        assert classify_claim_type("VA published a rule") == ClaimType.OBSERVED


# --- suggest_confidence ---


class TestSuggestConfidence:
    def test_modeled_with_sources_medium(self):
        assert suggest_confidence(2, ClaimType.MODELED) == Confidence.MEDIUM

    def test_modeled_no_sources_low(self):
        assert suggest_confidence(0, ClaimType.MODELED) == Confidence.LOW

    def test_inferred_two_sources_medium(self):
        assert suggest_confidence(2, ClaimType.INFERRED) == Confidence.MEDIUM

    def test_inferred_one_source_low(self):
        assert suggest_confidence(1, ClaimType.INFERRED) == Confidence.LOW

    def test_observed_two_primary_high(self):
        assert (
            suggest_confidence(2, ClaimType.OBSERVED, sources_are_primary=True) == Confidence.HIGH
        )

    def test_observed_one_primary_medium(self):
        assert (
            suggest_confidence(1, ClaimType.OBSERVED, sources_are_primary=True) == Confidence.MEDIUM
        )

    def test_observed_non_primary_low(self):
        assert (
            suggest_confidence(2, ClaimType.OBSERVED, sources_are_primary=False) == Confidence.LOW
        )
