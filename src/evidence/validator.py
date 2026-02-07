"""Hard-gated validation for Evidence Packs.

VALIDATION RULES:
1. No claim passes without citation
2. Citations must be dated
3. Citations must link to primary source
4. Modeled/inferred statements flagged separately

Fail-closed: If validation cannot be performed, reject the claim.
"""

from dataclasses import dataclass

from src.evidence.models import (
    ClaimType,
    Confidence,
    EvidenceClaim,
    EvidencePack,
    EvidenceSource,
    PackStatus,
)


@dataclass
class ValidationResult:
    """Result of validation check."""

    passed: bool
    errors: list[str]
    warnings: list[str]
    claim_index: int | None = None


class ValidationError(Exception):
    """Raised when validation fails hard."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"Validation failed: {'; '.join(errors)}")


def validate_source(source: EvidenceSource) -> ValidationResult:
    """
    Validate a single evidence source meets quality requirements.

    Requirements:
    - Must have URL (primary source link)
    - Must have access date
    - Should have publication date (warning if missing)
    """
    errors = []
    warnings = []

    # HARD REQUIREMENTS (fail if missing)
    if not source.url:
        errors.append(f"Source {source.source_id}: Missing URL (primary source link)")

    if not source.date_accessed:
        errors.append(f"Source {source.source_id}: Missing access date")

    # SOFT REQUIREMENTS (warn if missing)
    if not source.date_published:
        warnings.append(f"Source {source.source_id}: Missing publication date")

    if not source.title:
        warnings.append(f"Source {source.source_id}: Missing title")

    # Validate URL format (basic check)
    if source.url and not (source.url.startswith("http://") or source.url.startswith("https://")):
        errors.append(
            f"Source {source.source_id}: Invalid URL format (must start with http:// or https://)"
        )

    return ValidationResult(
        passed=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


def validate_claim(
    claim: EvidenceClaim, available_sources: dict[str, EvidenceSource], claim_index: int = 0
) -> ValidationResult:
    """
    Validate a single claim meets evidence requirements.

    Requirements:
    - Must have at least one supporting source
    - Supporting sources must exist
    - Observed claims must have direct citation
    - Modeled/inferred claims must be flagged appropriately
    """
    errors = []
    warnings = []

    # RULE 1: No claim without citation
    if not claim.source_ids:
        errors.append(f"Claim {claim_index + 1}: No supporting sources (every claim must be cited)")
    else:
        # Verify all source IDs exist
        for source_id in claim.source_ids:
            if source_id not in available_sources:
                errors.append(f"Claim {claim_index + 1}: References unknown source '{source_id}'")

    # RULE 4: Flag modeled/inferred separately
    if claim.claim_type == ClaimType.MODELED:
        if claim.confidence == Confidence.HIGH:
            warnings.append(
                f"Claim {claim_index + 1}: Modeled claim marked high confidence - verify methodology"
            )
        # Modeled claims should have explanation in the claim text or metadata
        if "model" not in claim.claim_text.lower() and "calculat" not in claim.claim_text.lower():
            warnings.append(
                f"Claim {claim_index + 1}: Modeled claim should indicate calculation methodology"
            )

    if claim.claim_type == ClaimType.INFERRED:
        if claim.confidence == Confidence.HIGH:
            warnings.append(
                f"Claim {claim_index + 1}: Inferred claim marked high confidence - consider downgrading"
            )

    # Low confidence claims should have multiple sources or explicit justification
    if claim.confidence == Confidence.LOW and len(claim.source_ids) == 1:
        warnings.append(
            f"Claim {claim_index + 1}: Low confidence with single source - consider adding corroboration"
        )

    return ValidationResult(
        passed=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        claim_index=claim_index,
    )


def validate_pack(pack: EvidencePack, strict: bool = True) -> ValidationResult:
    """
    Validate an entire evidence pack.

    Args:
        pack: The evidence pack to validate
        strict: If True, treat warnings as errors

    Returns:
        ValidationResult with overall pass/fail and all errors/warnings

    The pack's status is updated based on validation result.
    """
    all_errors = []
    all_warnings = []

    # Validate all sources first
    for source_id, source in pack.sources.items():
        result = validate_source(source)
        all_errors.extend(result.errors)
        all_warnings.extend(result.warnings)

        # RULE 2: Citations must be dated
        if not source.date_published and not source.date_accessed:
            all_errors.append(
                f"Source {source_id}: Must have either publication date or access date"
            )

        # RULE 3: Citations must link to primary source
        if not source.url:
            all_errors.append(f"Source {source_id}: Must have primary source URL")

    # Validate all claims
    for i, claim in enumerate(pack.claims):
        result = validate_claim(claim, pack.sources, i)
        all_errors.extend(result.errors)
        all_warnings.extend(result.warnings)

    # Pack-level validation
    if not pack.claims:
        all_warnings.append("Evidence pack has no claims")

    if not pack.sources:
        all_errors.append("Evidence pack has no sources")

    # Update pack status
    passed = len(all_errors) == 0
    if strict and all_warnings:
        passed = False
        all_errors.extend([f"[STRICT] {w}" for w in all_warnings])
        all_warnings = []

    pack.validation_errors = all_errors
    pack.status = PackStatus.VALIDATED if passed else PackStatus.FAILED

    return ValidationResult(
        passed=passed,
        errors=all_errors,
        warnings=all_warnings,
    )


def require_valid_pack(pack: EvidencePack, strict: bool = False) -> EvidencePack:
    """
    Validate pack and raise exception if invalid.

    This is the hard gate - use this before publishing or outputting.

    Args:
        pack: Evidence pack to validate
        strict: Whether to fail on warnings

    Returns:
        The validated pack (if valid)

    Raises:
        ValidationError: If pack fails validation
    """
    result = validate_pack(pack, strict=strict)
    if not result.passed:
        raise ValidationError(result.errors)
    return pack


def validate_claim_text_has_source(
    claim_text: str, source_ids: list[str], available_sources: dict[str, EvidenceSource]
) -> tuple[bool, list[str]]:
    """
    Quick validation that a claim text has valid supporting sources.

    Use this for inline validation during pack construction.

    Args:
        claim_text: The claim being made
        source_ids: Source IDs cited for this claim
        available_sources: Dict of available sources

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    errors = []

    if not source_ids:
        errors.append("Claim must have at least one supporting source")
        return (False, errors)

    for source_id in source_ids:
        if source_id not in available_sources:
            errors.append(f"Source '{source_id}' not found in available sources")

    return (len(errors) == 0, errors)


def classify_claim_type(
    claim_text: str, has_direct_quote: bool = False, has_calculation: bool = False
) -> ClaimType:
    """
    Suggest claim type based on claim characteristics.

    Args:
        claim_text: The claim text
        has_direct_quote: Whether claim includes direct quote from source
        has_calculation: Whether claim involves calculation/modeling

    Returns:
        Suggested ClaimType
    """
    text_lower = claim_text.lower()

    # Indicators of modeled claims
    modeling_indicators = [
        "estimated",
        "projected",
        "forecast",
        "model",
        "calculated",
        "approximately",
        "likely to",
        "expected to",
        "predicted",
    ]

    # Indicators of inferred claims
    inference_indicators = [
        "suggests",
        "implies",
        "indicates",
        "appears to",
        "seems to",
        "therefore",
        "consequently",
        "as a result",
        "based on this",
    ]

    if has_calculation or any(ind in text_lower for ind in modeling_indicators):
        return ClaimType.MODELED

    if not has_direct_quote and any(ind in text_lower for ind in inference_indicators):
        return ClaimType.INFERRED

    return ClaimType.OBSERVED


def suggest_confidence(
    num_sources: int, claim_type: ClaimType, sources_are_primary: bool = True
) -> Confidence:
    """
    Suggest confidence level based on evidence characteristics.

    Args:
        num_sources: Number of supporting sources
        claim_type: Type of claim
        sources_are_primary: Whether sources are primary (vs secondary)

    Returns:
        Suggested Confidence level
    """
    if claim_type == ClaimType.MODELED:
        # Modeled claims cap at medium unless methodology is verified
        return Confidence.MEDIUM if num_sources > 0 else Confidence.LOW

    if claim_type == ClaimType.INFERRED:
        # Inferred claims cap at medium
        if num_sources >= 2:
            return Confidence.MEDIUM
        return Confidence.LOW

    # Observed claims
    if num_sources >= 2 and sources_are_primary:
        return Confidence.HIGH
    if num_sources == 1 and sources_are_primary:
        return Confidence.MEDIUM
    return Confidence.LOW
