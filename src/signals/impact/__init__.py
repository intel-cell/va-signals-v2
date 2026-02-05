"""Impact Translation & Decision Frameworks module.

CHARLIE COMMAND - LOE 3
Mission: Translate policy changes into operational/business impact.

Components:
- ImpactMemo: CEO-grade impact assessments
- HeatMap: Risk matrix for issue prioritization
- ObjectionLibrary: Staff pushback responses
- PolicyToOperationsTranslator: Converts policy signals to impact memos
- Integrations: Inter-command data flows (ALPHA, BRAVO, DELTA)
"""

from .models import (
    ImpactMemo,
    PolicyHook,
    WhyItMatters,
    HeatMap,
    HeatMapIssue,
    Objection,
    Posture,
    ConfidenceLevel,
    RiskLevel,
    IssueArea,
    SourceType,
    HeatMapQuadrant,
)

from .translator import (
    PolicyToOperationsTranslator,
    TranslationContext,
    translate_bill_to_impact,
    translate_hearing_to_impact,
    translate_fr_to_impact,
)

from .heat_map_generator import (
    HeatMapGenerator,
    generate_heat_map,
    get_current_heat_map,
    render_heat_map_for_brief,
    assess_bill_likelihood,
    assess_bill_impact,
    assess_hearing_likelihood,
    assess_hearing_impact,
)

from .objection_library import (
    ObjectionLibrary,
    seed_objection_library,
    find_objection_response,
    get_objections_for_area,
    render_objection_for_brief,
)

from .integrations import (
    # DELTA Integration
    push_heat_scores_to_delta,
    batch_push_heat_scores,
    get_vehicles_needing_heat_scores,
    # ALPHA Integration
    get_impact_section_for_brief,
    get_risks_for_brief,
    get_objections_for_brief,
    # BRAVO Integration
    enrich_memo_with_evidence,
    find_evidence_for_source,
    get_citations_for_topic,
    # Pipeline
    run_charlie_integration,
    check_integration_status,
)

__all__ = [
    # Models
    "ImpactMemo",
    "PolicyHook",
    "WhyItMatters",
    "HeatMap",
    "HeatMapIssue",
    "Objection",
    # Enums
    "Posture",
    "ConfidenceLevel",
    "RiskLevel",
    "IssueArea",
    "SourceType",
    "HeatMapQuadrant",
    # Translator
    "PolicyToOperationsTranslator",
    "TranslationContext",
    "translate_bill_to_impact",
    "translate_hearing_to_impact",
    "translate_fr_to_impact",
    # Heat Map Generator
    "HeatMapGenerator",
    "generate_heat_map",
    "get_current_heat_map",
    "render_heat_map_for_brief",
    "assess_bill_likelihood",
    "assess_bill_impact",
    "assess_hearing_likelihood",
    "assess_hearing_impact",
    # Objection Library
    "ObjectionLibrary",
    "seed_objection_library",
    "find_objection_response",
    "get_objections_for_area",
    "render_objection_for_brief",
    # Integrations - DELTA
    "push_heat_scores_to_delta",
    "batch_push_heat_scores",
    "get_vehicles_needing_heat_scores",
    # Integrations - ALPHA
    "get_impact_section_for_brief",
    "get_risks_for_brief",
    "get_objections_for_brief",
    # Integrations - BRAVO
    "enrich_memo_with_evidence",
    "find_evidence_for_source",
    "get_citations_for_topic",
    # Integration Pipeline
    "run_charlie_integration",
    "check_integration_status",
]
