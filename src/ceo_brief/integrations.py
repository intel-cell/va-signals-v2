"""
CEO Brief Cross-Command Integrations.

Interfaces with BRAVO, CHARLIE, and DELTA commands for:
- Evidence citations (BRAVO)
- Impact memos and heat maps (CHARLIE)
- Decision points and battlefield status (DELTA)
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from .schema import (
    AskItem,
    IssueArea,
    Likelihood,
    ObjectionResponse,
    RiskOpportunity,
    SourceCitation,
    SourceType,
)

logger = logging.getLogger("ceo_brief.integrations")

# ============================================================================
# BRAVO COMMAND INTEGRATION - Evidence Packs
# ============================================================================


def _bravo_available() -> bool:
    """Check if BRAVO evidence API is available."""
    try:
        from src.evidence import api as evidence_api
        return hasattr(evidence_api, 'get_citations_for_topic')
    except ImportError:
        return False


def get_bravo_citations(
    topic: str,
    source_types: Optional[list[str]] = None,
    limit: int = 10,
) -> list[SourceCitation]:
    """
    Get relevant citations from BRAVO evidence packs.

    Args:
        topic: Search topic (e.g., "toxic exposure PACT Act")
        source_types: Filter by source types (e.g., ["bill", "gao_report"])
        limit: Maximum results

    Returns:
        List of SourceCitation objects
    """
    if not _bravo_available():
        logger.warning("BRAVO evidence API not available")
        return []

    try:
        from src.evidence.api import get_citations_for_topic

        results = get_citations_for_topic(topic, source_types=source_types, limit=limit)
        citations = []

        for r in results:
            source_type_map = {
                "federal_register": SourceType.FEDERAL_REGISTER,
                "bill": SourceType.BILL,
                "hearing": SourceType.HEARING,
                "gao_report": SourceType.GAO,
                "oig_report": SourceType.OIG,
                "crs_report": SourceType.CRS,
            }
            source_type = source_type_map.get(r.get("source_type"), SourceType.NEWS)

            pub_date = r.get("date_published") or r.get("date_accessed")
            if pub_date:
                try:
                    pub_date = date.fromisoformat(pub_date[:10])
                except (ValueError, TypeError):
                    pub_date = date.today()
            else:
                pub_date = date.today()

            citations.append(
                SourceCitation(
                    source_type=source_type,
                    source_id=r.get("source_id", ""),
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    date=pub_date,
                    excerpt=r.get("excerpt"),
                    section_ref=r.get("section_reference"),
                )
            )

        logger.info(f"BRAVO: Found {len(citations)} citations for topic '{topic}'")
        return citations

    except Exception as e:
        logger.error(f"BRAVO integration error: {e}")
        return []


def validate_claim_with_bravo(
    claim_text: str,
    source_ids: list[str],
) -> tuple[bool, list[str]]:
    """
    Validate a claim has proper supporting sources via BRAVO.

    Args:
        claim_text: The claim statement
        source_ids: List of source IDs cited

    Returns:
        Tuple of (is_valid, errors)
    """
    if not _bravo_available():
        logger.warning("BRAVO validation not available - failing closed")
        return False, ["BRAVO validation service unavailable"]

    try:
        from src.evidence.api import validate_claim
        return validate_claim(claim_text, source_ids)
    except Exception as e:
        logger.error(f"BRAVO validation error: {e}")
        return False, [f"BRAVO validation error: {str(e)}"]


def enrich_citation_from_bravo(citation: SourceCitation) -> SourceCitation:
    """
    Enrich a citation with BRAVO evidence pack data.

    Args:
        citation: Existing SourceCitation

    Returns:
        Enriched SourceCitation (or original if not found)
    """
    if not _bravo_available():
        return citation

    try:
        from src.evidence.api import get_source_by_id

        source = get_source_by_id(citation.source_id)
        if not source:
            return citation

        # Enrich with BRAVO data
        pub_date = source.get("date_published")
        if pub_date:
            try:
                pub_date = date.fromisoformat(pub_date[:10])
            except (ValueError, TypeError):
                pub_date = citation.date
        else:
            pub_date = citation.date

        return SourceCitation(
            source_type=citation.source_type,
            source_id=citation.source_id,
            title=source.get("title", citation.title),
            url=source.get("url", citation.url),
            date=pub_date,
            excerpt=citation.excerpt,
            section_ref=source.get("section_reference") or citation.section_ref,
        )

    except Exception as e:
        logger.error(f"BRAVO enrichment error: {e}")
        return citation


# ============================================================================
# CHARLIE COMMAND INTEGRATION - Impact Translation
# ============================================================================


def _charlie_available() -> bool:
    """Check if CHARLIE impact API is available."""
    try:
        from src.signals.impact import db as impact_db
        return hasattr(impact_db, 'get_impact_memos')
    except ImportError:
        return False


@dataclass
class ImpactData:
    """Impact data from CHARLIE for CEO Brief enhancement."""

    memos: list[dict]
    heat_map_text: Optional[str]
    high_priority_count: int
    objections: list[dict]


def get_charlie_impact_data() -> ImpactData:
    """
    Get impact memos, heat map, and objections from CHARLIE.

    Returns:
        ImpactData with memos, heat map visualization, and objections
    """
    if not _charlie_available():
        logger.warning("CHARLIE impact API not available")
        return ImpactData(memos=[], heat_map_text=None, high_priority_count=0, objections=[])

    try:
        from src.signals.impact.db import get_impact_memos, get_latest_heat_map
        from src.signals.impact.heat_map_generator import render_heat_map_for_brief
        from src.signals.impact.objection_library import get_objections_for_area

        # Get high-priority memos
        memos = []
        oppose_memos = get_impact_memos(posture="oppose", limit=3)
        engaged_memos = get_impact_memos(posture="neutral_engaged", limit=2)
        memos.extend(oppose_memos)
        memos.extend(engaged_memos)

        # Get heat map
        heat_map = get_latest_heat_map()
        heat_map_text = None
        high_priority_count = 0

        if heat_map:
            heat_map_text = render_heat_map_for_brief(heat_map)
            # Count high priority issues
            issues = heat_map.get("issues", [])
            high_priority_count = sum(
                1 for i in issues if i.get("quadrant") == "high_priority"
            )

        # Get objections from library
        objections = []
        for area in ["benefits", "accreditation", "claims_processing"]:
            area_objections = get_objections_for_area(area, limit=2)
            objections.extend(area_objections)

        logger.info(
            f"CHARLIE: Got {len(memos)} memos, {high_priority_count} high-priority issues, "
            f"{len(objections)} objections"
        )

        return ImpactData(
            memos=memos,
            heat_map_text=heat_map_text,
            high_priority_count=high_priority_count,
            objections=objections,
        )

    except Exception as e:
        logger.error(f"CHARLIE integration error: {e}")
        return ImpactData(memos=[], heat_map_text=None, high_priority_count=0, objections=[])


def charlie_memo_to_risk_opportunity(memo: dict) -> Optional[RiskOpportunity]:
    """Convert a CHARLIE impact memo to a RiskOpportunity for CEO Brief."""
    try:
        posture = memo.get("our_posture", "monitor")
        is_risk = posture == "oppose"

        compliance = memo.get("compliance_exposure", "medium")
        likelihood_map = {"critical": Likelihood.HIGH, "high": Likelihood.HIGH, "medium": Likelihood.MEDIUM}
        likelihood = likelihood_map.get(compliance, Likelihood.LOW)

        rep_risk = memo.get("reputational_risk", "low")
        impact_map = {"critical": Likelihood.HIGH, "high": Likelihood.HIGH, "medium": Likelihood.MEDIUM}
        impact = impact_map.get(rep_risk, Likelihood.LOW)

        return RiskOpportunity(
            description=memo.get("what_it_does", "")[:200],
            is_risk=is_risk,
            likelihood=likelihood,
            impact=impact,
            mitigation_or_action=memo.get("recommended_action"),
        )
    except Exception as e:
        logger.error(f"Error converting CHARLIE memo: {e}")
        return None


def charlie_objection_to_brief(objection: dict) -> Optional[ObjectionResponse]:
    """Convert a CHARLIE objection to an ObjectionResponse for CEO Brief."""
    try:
        return ObjectionResponse(
            objection=objection.get("objection_text", ""),
            response=objection.get("response_text", ""),
        )
    except Exception as e:
        logger.error(f"Error converting CHARLIE objection: {e}")
        return None


# ============================================================================
# DELTA COMMAND INTEGRATION - Battlefield Dashboard
# ============================================================================


def _delta_available() -> bool:
    """Check if DELTA battlefield API is available."""
    try:
        from src.battlefield import integrations as bf_int
        return hasattr(bf_int, 'get_decision_points_for_brief')
    except ImportError:
        return False


@dataclass
class BattlefieldData:
    """Battlefield data from DELTA for CEO Brief enhancement."""

    decision_points: list[dict]
    summary: dict
    critical_count: int


def get_delta_battlefield_data(days: int = 14) -> BattlefieldData:
    """
    Get decision points and battlefield summary from DELTA.

    Args:
        days: Number of days to look ahead for decision points

    Returns:
        BattlefieldData with decision points and summary
    """
    if not _delta_available():
        logger.warning("DELTA battlefield API not available")
        return BattlefieldData(decision_points=[], summary={}, critical_count=0)

    try:
        from src.battlefield.integrations import (
            get_decision_points_for_brief,
            get_active_vehicles_summary,
        )

        decision_points = get_decision_points_for_brief(days=days)
        summary = get_active_vehicles_summary()

        # Count critical decision points
        critical_count = sum(
            1 for dp in decision_points
            if dp.get("importance") == "critical"
        )

        logger.info(
            f"DELTA: Got {len(decision_points)} decision points ({critical_count} critical), "
            f"{summary.get('total', 0)} total vehicles"
        )

        return BattlefieldData(
            decision_points=decision_points,
            summary=summary,
            critical_count=critical_count,
        )

    except Exception as e:
        logger.error(f"DELTA integration error: {e}")
        return BattlefieldData(decision_points=[], summary={}, critical_count=0)


def delta_decision_point_to_ask(dp: dict) -> Optional[AskItem]:
    """Convert a DELTA decision point to an AskItem for CEO Brief."""
    try:
        event_type = dp.get("event_type", "")
        title = dp.get("title", "")
        dp_date = dp.get("date")

        action_map = {
            "hearing": "Prepare testimony or submit statement for the record",
            "markup": "Engage committee members before markup session",
            "vote": "Final engagement push before floor vote",
            "comment_deadline": "Submit public comments before deadline",
            "effective_date": "Ensure compliance readiness before effective date",
        }
        action = action_map.get(event_type, f"Prepare for {event_type}")

        deadline = None
        if dp_date:
            try:
                deadline = date.fromisoformat(dp_date[:10])
            except (ValueError, TypeError):
                pass

        importance = dp.get("importance", "watch")
        priority_map = {"critical": Likelihood.HIGH, "important": Likelihood.MEDIUM}
        priority = priority_map.get(importance, Likelihood.LOW)

        return AskItem(
            action=action,
            target=dp.get("location") or "Committee/Agency",
            deadline=deadline,
            rationale=title[:100],
            priority=priority,
        )
    except Exception as e:
        logger.error(f"Error converting DELTA decision point: {e}")
        return None


# ============================================================================
# COMBINED INTEGRATION
# ============================================================================


@dataclass
class CrossCommandData:
    """Combined data from all commands for enhanced CEO Brief."""

    # BRAVO
    citations_available: bool
    validation_available: bool

    # CHARLIE
    impact_data: ImpactData

    # DELTA
    battlefield_data: BattlefieldData


def gather_cross_command_data() -> CrossCommandData:
    """
    Gather all available cross-command data for CEO Brief enhancement.

    Returns:
        CrossCommandData with all available integration data
    """
    return CrossCommandData(
        citations_available=_bravo_available(),
        validation_available=_bravo_available(),
        impact_data=get_charlie_impact_data(),
        battlefield_data=get_delta_battlefield_data(),
    )
