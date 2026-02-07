"""Impact Translation Data Models.

CHARLIE COMMAND - Phase 1: Impact Memo Schema

These models translate policy signals into CEO-grade decision instruments.
The goal: a CEO reads the impact memo and understands the business decision,
not the policy details.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

# =============================================================================
# ENUMERATIONS
# =============================================================================


class Posture(str, Enum):
    """Our organization's posture on an issue."""

    SUPPORT = "support"
    OPPOSE = "oppose"
    MONITOR = "monitor"
    NEUTRAL_ENGAGED = "neutral_engaged"


class ConfidenceLevel(str, Enum):
    """Confidence in impact assessment."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RiskLevel(str, Enum):
    """Compliance or operational risk level."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NEGLIGIBLE = "negligible"


class IssueArea(str, Enum):
    """Primary issue domain for objections."""

    BENEFITS = "benefits"
    ACCREDITATION = "accreditation"
    APPROPRIATIONS = "appropriations"
    OVERSIGHT = "oversight"
    IT_MODERNIZATION = "it_modernization"
    CLAIMS_PROCESSING = "claims_processing"


class SourceType(str, Enum):
    """Source of objection/pushback."""

    STAFF = "staff"
    VSO = "vso"
    INDUSTRY = "industry"
    MEDIA = "media"
    CONGRESSIONAL = "congressional"
    VA_INTERNAL = "va_internal"


class HeatMapQuadrant(str, Enum):
    """Heat map quadrant classification."""

    HIGH_PRIORITY = "high_priority"  # High likelihood + High impact
    WATCH = "watch"  # Low likelihood + High impact
    MONITOR = "monitor"  # High likelihood + Low impact
    LOW = "low"  # Low likelihood + Low impact


# =============================================================================
# IMPACT MEMO COMPONENTS
# =============================================================================


@dataclass
class PolicyHook:
    """Links impact memo to its policy source.

    The policy_hook answers: "What exactly changed in what vehicle?"
    """

    vehicle: str  # Bill number (H.R. 1234), rule docket (RIN 2900-AQ66), etc.
    vehicle_type: str  # bill, rule, hearing, report, executive_order
    section_reference: str | None  # Specific section/paragraph if applicable
    current_status: str  # introduced, proposed_rule, final_rule, markup, etc.
    source_url: str  # Link to primary source
    effective_date: str | None  # ISO date when change takes effect (if known)


@dataclass
class WhyItMatters:
    """Operational and business impact assessment.

    Translates policy change into business terms CEOs understand.
    Quantify when possible (even ranges: "could affect 10K-50K claims").
    """

    # Operational Impact
    operational_impact: str  # Plain language: claims volume, cycle time, staffing
    affected_workflows: list[str]  # claims_intake, rating, appeals, exam_scheduling, etc.
    affected_veteran_count: str | None  # Estimate or range ("~100K", "50K-200K")

    # Compliance Exposure
    compliance_exposure: RiskLevel
    enforcement_mechanism: str | None  # OIG audit, GAO review, court challenge, etc.
    compliance_deadline: str | None  # ISO date if regulatory deadline

    # Cost Impact
    cost_impact: str | None  # Quantified if possible: "$2-5M annual", "TBD"
    cost_type: str | None  # staffing, IT, contracts, benefits_increase

    # Reputational Risk
    reputational_risk: RiskLevel
    narrative_vulnerability: str | None  # How media/VSOs might frame this


# =============================================================================
# IMPACT MEMO - MAIN SCHEMA
# =============================================================================


@dataclass
class ImpactMemo:
    """CEO-grade impact assessment for a policy change.

    Schema per ORDER_CHARLIE_001:
    - memo_id: Unique identifier
    - issue_id: Links to tracked issue/signal
    - generated_date: When memo was created
    - policy_hook: What changed (vehicle, section, status)
    - what_it_does: Plain language summary (2-3 sentences)
    - why_it_matters: Operational, compliance, cost, reputational impact
    - our_posture: support|oppose|monitor|neutral_engaged
    - recommended_action: What CEO should do
    - decision_trigger: "if X appears, do Y"
    - confidence_level: high|medium|low
    - sources: Links to evidence pack
    """

    memo_id: str
    issue_id: str
    generated_date: str  # ISO datetime

    # What Changed
    policy_hook: PolicyHook
    what_it_does: str  # Plain language, 2-3 sentences

    # Why It Matters
    why_it_matters: WhyItMatters

    # Our Position
    our_posture: Posture
    recommended_action: str
    decision_trigger: str  # "if X appears, do Y"

    # Metadata
    confidence_level: ConfidenceLevel
    sources: list[str] = field(default_factory=list)  # Evidence pack links

    # Audit
    translated_by: str = "charlie_command"
    translation_method: str = "rule_based"  # or "llm", "manual"

    def to_dict(self) -> dict:
        """Serialize to dictionary for storage/API."""
        return {
            "memo_id": self.memo_id,
            "issue_id": self.issue_id,
            "generated_date": self.generated_date,
            "policy_hook": {
                "vehicle": self.policy_hook.vehicle,
                "vehicle_type": self.policy_hook.vehicle_type,
                "section_reference": self.policy_hook.section_reference,
                "current_status": self.policy_hook.current_status,
                "source_url": self.policy_hook.source_url,
                "effective_date": self.policy_hook.effective_date,
            },
            "what_it_does": self.what_it_does,
            "why_it_matters": {
                "operational_impact": self.why_it_matters.operational_impact,
                "affected_workflows": self.why_it_matters.affected_workflows,
                "affected_veteran_count": self.why_it_matters.affected_veteran_count,
                "compliance_exposure": self.why_it_matters.compliance_exposure.value,
                "enforcement_mechanism": self.why_it_matters.enforcement_mechanism,
                "compliance_deadline": self.why_it_matters.compliance_deadline,
                "cost_impact": self.why_it_matters.cost_impact,
                "cost_type": self.why_it_matters.cost_type,
                "reputational_risk": self.why_it_matters.reputational_risk.value,
                "narrative_vulnerability": self.why_it_matters.narrative_vulnerability,
            },
            "our_posture": self.our_posture.value,
            "recommended_action": self.recommended_action,
            "decision_trigger": self.decision_trigger,
            "confidence_level": self.confidence_level.value,
            "sources": self.sources,
            "translated_by": self.translated_by,
            "translation_method": self.translation_method,
        }


# =============================================================================
# HEAT MAP SCHEMA
# =============================================================================


@dataclass
class HeatMapIssue:
    """Single issue in the heat map.

    Score = likelihood x impact x urgency_factor
    Urgency factor increases as decision point approaches.
    """

    issue_id: str
    title: str
    likelihood: int  # 1-5 scale
    impact: int  # 1-5 scale
    urgency_days: int  # Days to next decision point
    score: float  # Calculated: likelihood * impact * urgency_factor
    quadrant: HeatMapQuadrant
    memo_id: str | None = None  # Link to impact memo if exists

    @classmethod
    def calculate_score(cls, likelihood: int, impact: int, urgency_days: int) -> float:
        """Calculate priority score with urgency factor.

        Urgency factor:
        - 0-7 days: 2.0x
        - 8-14 days: 1.5x
        - 15-30 days: 1.2x
        - 31+ days: 1.0x
        """
        if urgency_days <= 7:
            urgency_factor = 2.0
        elif urgency_days <= 14:
            urgency_factor = 1.5
        elif urgency_days <= 30:
            urgency_factor = 1.2
        else:
            urgency_factor = 1.0

        return likelihood * impact * urgency_factor

    @classmethod
    def determine_quadrant(cls, likelihood: int, impact: int) -> HeatMapQuadrant:
        """Determine heat map quadrant based on likelihood and impact.

                 HIGH IMPACT
                    |
          WATCH    |  HIGH PRIORITY
                   |
        <----------+---------->  HIGH LIKELIHOOD
                   |
          LOW      |  MONITOR
                    |
                 LOW IMPACT
        """
        high_likelihood = likelihood >= 3
        high_impact = impact >= 3

        if high_likelihood and high_impact:
            return HeatMapQuadrant.HIGH_PRIORITY
        elif not high_likelihood and high_impact:
            return HeatMapQuadrant.WATCH
        elif high_likelihood and not high_impact:
            return HeatMapQuadrant.MONITOR
        else:
            return HeatMapQuadrant.LOW


@dataclass
class HeatMap:
    """Risk matrix showing all active issues.

    Schema per ORDER_CHARLIE_001:
    - generated_date
    - issues[]: list of HeatMapIssue
    """

    heat_map_id: str
    generated_date: str  # ISO datetime
    issues: list[HeatMapIssue]

    def get_high_priority(self) -> list[HeatMapIssue]:
        """Get issues in HIGH_PRIORITY quadrant, sorted by score."""
        return sorted(
            [i for i in self.issues if i.quadrant == HeatMapQuadrant.HIGH_PRIORITY],
            key=lambda x: x.score,
            reverse=True,
        )

    def get_watch_list(self) -> list[HeatMapIssue]:
        """Get issues in WATCH quadrant."""
        return sorted(
            [i for i in self.issues if i.quadrant == HeatMapQuadrant.WATCH],
            key=lambda x: x.score,
            reverse=True,
        )

    def to_dict(self) -> dict:
        """Serialize for storage/API."""
        return {
            "heat_map_id": self.heat_map_id,
            "generated_date": self.generated_date,
            "issues": [
                {
                    "issue_id": i.issue_id,
                    "title": i.title,
                    "likelihood": i.likelihood,
                    "impact": i.impact,
                    "urgency_days": i.urgency_days,
                    "score": i.score,
                    "quadrant": i.quadrant.value,
                    "memo_id": i.memo_id,
                }
                for i in self.issues
            ],
            "summary": {
                "total_issues": len(self.issues),
                "high_priority_count": len(self.get_high_priority()),
                "watch_count": len(self.get_watch_list()),
            },
        }

    def render_ascii(self) -> str:
        """Render 2x2 matrix as ASCII for CEO Brief.

        Output format per ORDER_CHARLIE_001:
                   HIGH IMPACT
                      |
            WATCH    |  HIGH PRIORITY
                     |
          <----------+---------->  HIGH LIKELIHOOD
                     |
            LOW      |  MONITOR
                      |
                   LOW IMPACT
        """
        high_priority = self.get_high_priority()
        watch = self.get_watch_list()
        monitor = [i for i in self.issues if i.quadrant == HeatMapQuadrant.MONITOR]
        low = [i for i in self.issues if i.quadrant == HeatMapQuadrant.LOW]

        def format_issues(issues: list, max_items: int = 3) -> str:
            if not issues:
                return "  (none)"
            lines = []
            for i in issues[:max_items]:
                lines.append(f"  - {i.title[:30]}... (L:{i.likelihood} I:{i.impact})")
            if len(issues) > max_items:
                lines.append(f"  + {len(issues) - max_items} more")
            return "\n".join(lines)

        return f"""
==================== HEAT MAP ====================
Generated: {self.generated_date}

                    HIGH IMPACT
                        |
   WATCH ({len(watch)})           |  HIGH PRIORITY ({len(high_priority)})
{format_issues(watch)}      |  {format_issues(high_priority)}
                        |
   <--------------------+-------------------->  HIGH LIKELIHOOD
                        |
   LOW ({len(low)})              |  MONITOR ({len(monitor)})
{format_issues(low)}      |  {format_issues(monitor)}
                        |
                    LOW IMPACT
======================================================
"""


# =============================================================================
# OBJECTION LIBRARY SCHEMA
# =============================================================================


@dataclass
class Objection:
    """Staff pushback response entry.

    Schema per ORDER_CHARLIE_001:
    - objection_id
    - issue_area (benefits|accreditation|appropriations)
    - source_type (staff|VSO|industry|media)
    - objection_text (what they'll say)
    - response_text (1-2 sentence reply)
    - supporting_evidence[] (links to evidence pack)
    - last_used_date
    - effectiveness_rating
    """

    objection_id: str
    issue_area: IssueArea
    source_type: SourceType
    objection_text: str  # What they'll say
    response_text: str  # 1-2 sentence reply
    supporting_evidence: list[str]  # Links to evidence pack
    last_used_date: str | None = None  # ISO datetime
    effectiveness_rating: int | None = None  # 1-5 scale, updated based on feedback
    tags: list[str] = field(default_factory=list)  # Additional categorization

    def to_dict(self) -> dict:
        """Serialize for storage/API."""
        return {
            "objection_id": self.objection_id,
            "issue_area": self.issue_area.value,
            "source_type": self.source_type.value,
            "objection_text": self.objection_text,
            "response_text": self.response_text,
            "supporting_evidence": self.supporting_evidence,
            "last_used_date": self.last_used_date,
            "effectiveness_rating": self.effectiveness_rating,
            "tags": self.tags,
        }


# =============================================================================
# FACTORY FUNCTIONS
# =============================================================================


def create_impact_memo(
    issue_id: str,
    vehicle: str,
    vehicle_type: str,
    current_status: str,
    source_url: str,
    what_it_does: str,
    operational_impact: str,
    affected_workflows: list[str],
    compliance_exposure: RiskLevel,
    reputational_risk: RiskLevel,
    posture: Posture,
    recommended_action: str,
    decision_trigger: str,
    confidence: ConfidenceLevel,
    sources: list[str],
    section_reference: str | None = None,
    effective_date: str | None = None,
    affected_veteran_count: str | None = None,
    enforcement_mechanism: str | None = None,
    compliance_deadline: str | None = None,
    cost_impact: str | None = None,
    cost_type: str | None = None,
    narrative_vulnerability: str | None = None,
) -> ImpactMemo:
    """Factory function to create Impact Memo with sensible defaults."""
    import uuid

    now = datetime.now(UTC)
    memo_id = f"MEMO-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"

    policy_hook = PolicyHook(
        vehicle=vehicle,
        vehicle_type=vehicle_type,
        section_reference=section_reference,
        current_status=current_status,
        source_url=source_url,
        effective_date=effective_date,
    )

    why_it_matters = WhyItMatters(
        operational_impact=operational_impact,
        affected_workflows=affected_workflows,
        affected_veteran_count=affected_veteran_count,
        compliance_exposure=compliance_exposure,
        enforcement_mechanism=enforcement_mechanism,
        compliance_deadline=compliance_deadline,
        cost_impact=cost_impact,
        cost_type=cost_type,
        reputational_risk=reputational_risk,
        narrative_vulnerability=narrative_vulnerability,
    )

    return ImpactMemo(
        memo_id=memo_id,
        issue_id=issue_id,
        generated_date=now.isoformat().replace("+00:00", "Z"),
        policy_hook=policy_hook,
        what_it_does=what_it_does,
        why_it_matters=why_it_matters,
        our_posture=posture,
        recommended_action=recommended_action,
        decision_trigger=decision_trigger,
        confidence_level=confidence,
        sources=sources,
    )


def create_heat_map_issue(
    issue_id: str,
    title: str,
    likelihood: int,
    impact: int,
    urgency_days: int,
    memo_id: str | None = None,
) -> HeatMapIssue:
    """Factory function to create HeatMapIssue with calculated fields."""
    score = HeatMapIssue.calculate_score(likelihood, impact, urgency_days)
    quadrant = HeatMapIssue.determine_quadrant(likelihood, impact)

    return HeatMapIssue(
        issue_id=issue_id,
        title=title,
        likelihood=likelihood,
        impact=impact,
        urgency_days=urgency_days,
        score=score,
        quadrant=quadrant,
        memo_id=memo_id,
    )
