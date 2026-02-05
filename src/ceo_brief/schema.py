"""
CEO Brief Schema - Data structures for the weekly CEO Lobbyist Brief.

The CEO Brief is the flagship output: a 1-2 page decision-ready instrument
that transforms raw policy signals into speakable talking points, stakeholder
maps, and specific asks for the lobbying team.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional


class IssueArea(str, Enum):
    """Classification of policy issues by functional area."""

    BENEFITS_CLAIMS = "benefits_claims"
    ACCREDITATION = "accreditation"
    APPROPRIATIONS = "appropriations"
    HEALTHCARE = "healthcare"
    TECHNOLOGY = "technology"
    STAFFING = "staffing"
    OVERSIGHT = "oversight"
    LEGAL = "legal"
    STATE = "state"
    OTHER = "other"


class Likelihood(str, Enum):
    """Probability assessment for risks/opportunities."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Impact(str, Enum):
    """Impact severity for risks/opportunities."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SourceType(str, Enum):
    """Types of primary sources for citations."""

    FEDERAL_REGISTER = "federal_register"
    BILL = "bill"
    HEARING = "hearing"
    OVERSIGHT = "oversight"
    STATE = "state"
    ECFR = "ecfr"
    GAO = "gao"
    OIG = "oig"
    CRS = "crs"
    NEWS = "news"


@dataclass
class SourceCitation:
    """
    Hard-gated source citation - every claim must link to a primary source.

    Provides receipt with date for credibility with staffers and policymakers.
    """

    source_type: SourceType
    source_id: str  # e.g., FR doc number, bill_id, event_id
    title: str
    url: str
    date: date
    excerpt: Optional[str] = None  # Relevant text snippet
    section_ref: Optional[str] = None  # e.g., "Section 3(a)", "38 CFR 21.4250"


@dataclass
class Message:
    """
    Exact talking point - speakable phrasing the CEO can actually say.

    Not a summary or description - this is the line to deliver.
    """

    text: str  # The exact words to say
    context: str  # Brief background (for CEO preparation, not delivery)
    supporting_citations: list[SourceCitation] = field(default_factory=list)


@dataclass
class Stakeholder:
    """
    Stakeholder mapping - who matters and why they care.

    Helps CEO target conversations and understand motivations.
    """

    name: str  # Person or organization name
    role: str  # Title or position
    why_they_care: str  # Their interest/stake in the issue
    relationship_note: Optional[str] = None  # Any existing relationship context
    priority: Likelihood = Likelihood.MEDIUM  # How important to engage


@dataclass
class RiskOpportunity:
    """
    Risk or opportunity assessment with likelihood and impact.

    Supports 2x2 matrix visualization (likelihood x impact).
    """

    description: str
    is_risk: bool  # True = risk, False = opportunity
    likelihood: Likelihood
    impact: Impact
    mitigation_or_action: Optional[str] = None  # What to do about it
    supporting_citations: list[SourceCitation] = field(default_factory=list)


@dataclass
class AskItem:
    """
    Specific ask for the lobbying team - explicit action, not "build relationships".

    Must be actionable: who, what, when.
    """

    action: str  # What specifically to do
    target: str  # Who to target (person/organization)
    deadline: Optional[date] = None  # When it needs to happen
    rationale: str = ""  # Why this matters now
    priority: Likelihood = Likelihood.MEDIUM


@dataclass
class IssueSnapshot:
    """
    Issue snapshot - max 3 per brief.

    Provides policy hook, plain-language explanation, and specific line change.
    """

    issue_area: IssueArea
    policy_hook: str  # Bill section, reg cite (e.g., "H.R. 1234 Section 5", "38 CFR 21.4250")
    what_it_does: str  # Plain language explanation
    why_it_matters: str  # Business/operational impact
    line_we_want: str  # Specific insert/remove/change requested
    is_insert: bool  # True = add language, False = remove/modify
    supporting_citations: list[SourceCitation] = field(default_factory=list)


@dataclass
class ObjectionResponse:
    """
    Objection-response pair for common staff pushbacks.

    Prepares CEO for likely questions/resistance.
    """

    objection: str  # The pushback they'll likely raise
    response: str  # The counter-argument
    supporting_citations: list[SourceCitation] = field(default_factory=list)


@dataclass
class Delta:
    """
    Change since last brief - what's new/different.

    Keeps CEO current without re-reading everything.
    """

    description: str
    source_type: SourceType
    source_id: str
    change_date: date
    issue_area: IssueArea
    significance: Likelihood  # How important is this change


@dataclass
class CEOBrief:
    """
    The complete CEO Lobbyist Brief - 1-2 page decision instrument.

    Success criteria (CEO test):
    - What do I say? (messages)
    - To whom? (stakeholder_map)
    - When? (ask_list deadlines)
    - What's the ask? (ask_list actions)

    All claims must link to dated, sourced evidence.
    """

    # Metadata
    generated_at: datetime
    period_start: date
    period_end: date
    brief_id: str  # Unique identifier for this brief

    # Strategic framing
    objective: str  # One sentence: what we're trying to achieve this week

    # Core content
    messages: list[Message]  # Exactly 3 talking points
    stakeholder_map: list[Stakeholder]  # 5-10 key stakeholders
    deltas: list[Delta]  # What changed since last week
    risks_opportunities: list[RiskOpportunity]  # 2x2 or bullets
    ask_list: list[AskItem]  # 3-7 specific actions

    # Deep dives (max 3)
    issue_snapshots: list[IssueSnapshot]

    # Preparation
    objections_responses: list[ObjectionResponse]  # Top 3 pushbacks + replies

    # Provenance
    sources: list[SourceCitation]  # All sources cited in brief

    def validate(self) -> list[str]:
        """
        Validate brief against quality gates.

        Returns list of validation errors (empty = valid).
        """
        errors = []

        # Message count
        if len(self.messages) != 3:
            errors.append(f"Expected exactly 3 messages, got {len(self.messages)}")

        # Stakeholder count
        if not (5 <= len(self.stakeholder_map) <= 10):
            errors.append(
                f"Expected 5-10 stakeholders, got {len(self.stakeholder_map)}"
            )

        # Ask list count
        if not (3 <= len(self.ask_list) <= 7):
            errors.append(f"Expected 3-7 asks, got {len(self.ask_list)}")

        # Issue snapshot count
        if len(self.issue_snapshots) > 3:
            errors.append(
                f"Expected max 3 issue snapshots, got {len(self.issue_snapshots)}"
            )

        # Objection-response count
        if len(self.objections_responses) < 3:
            errors.append(
                f"Expected at least 3 objection-responses, got {len(self.objections_responses)}"
            )

        # Citation validation - every message must have sources
        for i, msg in enumerate(self.messages):
            if not msg.supporting_citations:
                errors.append(f"Message {i + 1} has no supporting citations")

        # Issue snapshots must have citations
        for i, snapshot in enumerate(self.issue_snapshots):
            if not snapshot.supporting_citations:
                errors.append(f"Issue snapshot {i + 1} has no supporting citations")

        return errors

    def to_markdown(self) -> str:
        """Generate markdown output for the brief."""
        lines = []

        # Header
        lines.append(f"# CEO Lobbyist Brief")
        lines.append(f"**Generated:** {self.generated_at.strftime('%Y-%m-%d %H:%M UTC')}")
        lines.append(f"**Period:** {self.period_start} to {self.period_end}")
        lines.append("")

        # Objective
        lines.append("## Objective")
        lines.append(self.objective)
        lines.append("")

        # Messages (Talking Points)
        lines.append("## Key Messages")
        for i, msg in enumerate(self.messages, 1):
            lines.append(f"### {i}. {msg.text}")
            lines.append(f"*Context: {msg.context}*")
            if msg.supporting_citations:
                refs = ", ".join(
                    f"[{c.source_id}]({c.url})" for c in msg.supporting_citations
                )
                lines.append(f"Sources: {refs}")
            lines.append("")

        # Stakeholder Map
        lines.append("## Stakeholder Map")
        for s in self.stakeholder_map:
            priority_marker = {"high": "!!!", "medium": "!!", "low": "!"}.get(
                s.priority.value, ""
            )
            lines.append(f"- **{s.name}** ({s.role}) {priority_marker}")
            lines.append(f"  - Why they care: {s.why_they_care}")
            if s.relationship_note:
                lines.append(f"  - Note: {s.relationship_note}")
        lines.append("")

        # Deltas
        if self.deltas:
            lines.append("## What Changed This Week")
            for d in self.deltas:
                lines.append(
                    f"- [{d.change_date}] **{d.issue_area.value}**: {d.description}"
                )
            lines.append("")

        # Risks & Opportunities
        lines.append("## Risks & Opportunities")
        risks = [r for r in self.risks_opportunities if r.is_risk]
        opps = [r for r in self.risks_opportunities if not r.is_risk]

        if risks:
            lines.append("### Risks")
            for r in risks:
                lines.append(
                    f"- [{r.likelihood.value.upper()}/{r.impact.value.upper()}] {r.description}"
                )
                if r.mitigation_or_action:
                    lines.append(f"  - Mitigation: {r.mitigation_or_action}")

        if opps:
            lines.append("### Opportunities")
            for o in opps:
                lines.append(
                    f"- [{o.likelihood.value.upper()}/{o.impact.value.upper()}] {o.description}"
                )
                if o.mitigation_or_action:
                    lines.append(f"  - Action: {o.mitigation_or_action}")
        lines.append("")

        # Ask List
        lines.append("## Ask List")
        for i, ask in enumerate(self.ask_list, 1):
            deadline = f" (by {ask.deadline})" if ask.deadline else ""
            lines.append(f"{i}. **{ask.action}**{deadline}")
            lines.append(f"   - Target: {ask.target}")
            if ask.rationale:
                lines.append(f"   - Why: {ask.rationale}")
        lines.append("")

        # Issue Snapshots
        if self.issue_snapshots:
            lines.append("## Issue Snapshots")
            for snapshot in self.issue_snapshots:
                lines.append(f"### {snapshot.policy_hook}")
                lines.append(f"**What it does:** {snapshot.what_it_does}")
                lines.append(f"**Why it matters:** {snapshot.why_it_matters}")
                action = "INSERT" if snapshot.is_insert else "CHANGE/REMOVE"
                lines.append(f"**Our line ({action}):** {snapshot.line_we_want}")
                if snapshot.supporting_citations:
                    refs = ", ".join(
                        f"[{c.source_id}]({c.url})"
                        for c in snapshot.supporting_citations
                    )
                    lines.append(f"*Sources: {refs}*")
                lines.append("")

        # Objections & Responses
        lines.append("## Anticipated Objections")
        for i, obj in enumerate(self.objections_responses, 1):
            lines.append(f"### {i}. \"{obj.objection}\"")
            lines.append(f"**Response:** {obj.response}")
            if obj.supporting_citations:
                refs = ", ".join(
                    f"[{c.source_id}]({c.url})" for c in obj.supporting_citations
                )
                lines.append(f"*Sources: {refs}*")
            lines.append("")

        # Sources
        lines.append("---")
        lines.append("## Sources")
        for s in self.sources:
            lines.append(f"- [{s.source_id}]({s.url}) - {s.title} ({s.date})")

        return "\n".join(lines)


@dataclass
class AggregatedDelta:
    """
    Raw delta from source aggregation - input to analyst agent.

    Contains all source data before analysis and prioritization.
    """

    source_type: SourceType
    source_id: str
    title: str
    url: str
    published_date: date
    first_seen_at: datetime
    issue_area: IssueArea
    raw_content: Optional[str] = None
    summary: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    # Scoring for prioritization
    impact_score: float = 0.0  # 0-1, higher = more important
    urgency_score: float = 0.0  # 0-1, higher = more urgent
    relevance_score: float = 0.0  # 0-1, higher = more relevant to VA claims


@dataclass
class AggregationResult:
    """
    Result of aggregation phase - all deltas from all sources.

    Passed to analyst agent for processing.
    """

    period_start: date
    period_end: date
    aggregated_at: datetime

    # Raw deltas by source
    fr_deltas: list[AggregatedDelta] = field(default_factory=list)
    bill_deltas: list[AggregatedDelta] = field(default_factory=list)
    hearing_deltas: list[AggregatedDelta] = field(default_factory=list)
    oversight_deltas: list[AggregatedDelta] = field(default_factory=list)
    state_deltas: list[AggregatedDelta] = field(default_factory=list)

    @property
    def all_deltas(self) -> list[AggregatedDelta]:
        """All deltas combined and sorted by impact score."""
        all_d = (
            self.fr_deltas
            + self.bill_deltas
            + self.hearing_deltas
            + self.oversight_deltas
            + self.state_deltas
        )
        return sorted(all_d, key=lambda d: d.impact_score, reverse=True)

    @property
    def total_count(self) -> int:
        return len(self.all_deltas)


@dataclass
class AnalysisResult:
    """
    Result of analyst phase - prioritized issues with drafted content.

    Passed to brief generator for final compilation.
    """

    # Top issues identified
    top_issues: list[AggregatedDelta]  # Max 5, ranked by priority

    # Drafted content
    draft_messages: list[Message]
    draft_stakeholders: list[Stakeholder]
    draft_risks_opps: list[RiskOpportunity]
    draft_asks: list[AskItem]
    draft_snapshots: list[IssueSnapshot]
    draft_objections: list[ObjectionResponse]

    # Metadata
    analyzed_at: datetime
    total_deltas_reviewed: int
    issues_identified: int
