"""Evidence Pack module for source-of-truth system.

BRAVO COMMAND: Build and deploy an Evidence Pack system that provides
dated, versioned, citable sources for all intelligence outputs.

Key components:
- models: Data structures for evidence packs, sources, claims
- extractors: Citation extractors for each source type
- generator: Evidence pack generation from issues/claims
- validator: Hard-gated validation (no claim without source)
- api: Integration API for other commands
- alpha_integration: ALPHA COMMAND integration (CEO Brief)
"""

from src.evidence.models import (
    EvidencePack,
    EvidenceSource,
    EvidenceExcerpt,
    EvidenceClaim,
    SourceType,
    ClaimType,
    Confidence,
)
from src.evidence.validator import validate_claim, validate_pack
from src.evidence.api import (
    get_evidence_pack,
    validate_claim as api_validate_claim,
    get_citations_for_topic,
)
from src.evidence.alpha_integration import (
    SourceCitationForAlpha,
    evidence_source_to_alpha_citation,
    find_evidence_for_source,
    get_citations_for_brief,
    validate_brief_citations,
    enrich_brief_with_evidence,
)
from src.evidence.delta_integration import (
    get_vehicles_needing_evidence_packs,
    get_vehicle_details,
    link_evidence_pack_to_vehicle,
    batch_link_evidence_packs,
    generate_evidence_pack_for_vehicle,
    batch_generate_evidence_packs,
    get_evidence_for_vehicle,
    get_vehicles_with_evidence_summary,
)

__all__ = [
    # Models
    "EvidencePack",
    "EvidenceSource",
    "EvidenceExcerpt",
    "EvidenceClaim",
    "SourceType",
    "ClaimType",
    "Confidence",
    # Validation
    "validate_claim",
    "validate_pack",
    # API
    "get_evidence_pack",
    "api_validate_claim",
    "get_citations_for_topic",
    # ALPHA Integration
    "SourceCitationForAlpha",
    "evidence_source_to_alpha_citation",
    "find_evidence_for_source",
    "get_citations_for_brief",
    "validate_brief_citations",
    "enrich_brief_with_evidence",
    # DELTA Integration
    "get_vehicles_needing_evidence_packs",
    "get_vehicle_details",
    "link_evidence_pack_to_vehicle",
    "batch_link_evidence_packs",
    "generate_evidence_pack_for_vehicle",
    "batch_generate_evidence_packs",
    "get_evidence_for_vehicle",
    "get_vehicles_with_evidence_summary",
]
