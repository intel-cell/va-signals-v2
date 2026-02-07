"""CEO Brief Pipeline - Automated weekly decision instrument generator."""

from .aggregator import aggregate_deltas, get_top_deltas
from .analyst import analyze_deltas
from .generator import (
    generate_and_save_brief,
    generate_and_save_enhanced_brief,
    generate_brief,
    generate_enhanced_brief,
    save_brief,
)
from .integrations import gather_cross_command_data
from .runner import PipelineResult, run_pipeline
from .schema import (
    AggregatedDelta,
    AggregationResult,
    AnalysisResult,
    CEOBrief,
    IssueArea,
    IssueSnapshot,
    Message,
    ObjectionResponse,
    RiskOpportunity,
    SourceCitation,
    SourceType,
    Stakeholder,
)

__all__ = [
    # Runner
    "run_pipeline",
    "PipelineResult",
    # Aggregator
    "aggregate_deltas",
    "get_top_deltas",
    # Analyst
    "analyze_deltas",
    # Generator
    "generate_brief",
    "save_brief",
    "generate_and_save_brief",
    "generate_enhanced_brief",
    "generate_and_save_enhanced_brief",
    # Integrations
    "gather_cross_command_data",
    # Schema
    "AggregatedDelta",
    "AggregationResult",
    "AnalysisResult",
    "CEOBrief",
    "IssueArea",
    "IssueSnapshot",
    "Message",
    "ObjectionResponse",
    "RiskOpportunity",
    "SourceCitation",
    "SourceType",
    "Stakeholder",
]
