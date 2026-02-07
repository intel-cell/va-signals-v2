"""
CEO Brief Analyst Agent.

Reviews aggregated deltas, identifies top 3-5 issues requiring CEO attention,
drafts talking points, maps stakeholders, and generates ask list.
"""

from datetime import date, datetime

from .aggregator import get_top_deltas
from .schema import (
    AggregatedDelta,
    AggregationResult,
    AnalysisResult,
    AskItem,
    IssueArea,
    IssueSnapshot,
    Likelihood,
    Message,
    ObjectionResponse,
    RiskOpportunity,
    SourceCitation,
    SourceType,
    Stakeholder,
)

# Stakeholder templates by issue area
STAKEHOLDER_TEMPLATES = {
    IssueArea.BENEFITS_CLAIMS: [
        Stakeholder(
            name="VA Under Secretary for Benefits",
            role="VBA Leadership",
            why_they_care="Responsible for claims processing performance and backlog reduction",
            priority=Likelihood.HIGH,
        ),
        Stakeholder(
            name="House Veterans Affairs Committee",
            role="Congressional Oversight",
            why_they_care="Oversight of VA claims processing; frequent hearings on backlog",
            priority=Likelihood.HIGH,
        ),
        Stakeholder(
            name="Senate Veterans Affairs Committee",
            role="Congressional Oversight",
            why_they_care="Confirms VA leadership; authorizes policy changes",
            priority=Likelihood.HIGH,
        ),
        Stakeholder(
            name="American Legion",
            role="VSO Partner",
            why_they_care="Represents veterans in claims process; accredited agents",
            priority=Likelihood.MEDIUM,
        ),
        Stakeholder(
            name="Veterans of Foreign Wars (VFW)",
            role="VSO Partner",
            why_they_care="Major VSO with claims assistance programs",
            priority=Likelihood.MEDIUM,
        ),
    ],
    IssueArea.ACCREDITATION: [
        Stakeholder(
            name="VA Office of General Counsel",
            role="Accreditation Authority",
            why_they_care="Oversees accreditation of claims agents and attorneys",
            priority=Likelihood.HIGH,
        ),
        Stakeholder(
            name="National Organization of Veterans' Advocates (NOVA)",
            role="Attorney Association",
            why_they_care="Represents accredited attorneys; fee regulation impacts",
            priority=Likelihood.HIGH,
        ),
        Stakeholder(
            name="VA Board of Veterans' Appeals",
            role="Appellate Body",
            why_they_care="Adjudicates appeals; works with accredited representatives",
            priority=Likelihood.MEDIUM,
        ),
    ],
    IssueArea.APPROPRIATIONS: [
        Stakeholder(
            name="House Appropriations - MILCON-VA Subcommittee",
            role="Funding Authority",
            why_they_care="Controls VA discretionary spending",
            priority=Likelihood.HIGH,
        ),
        Stakeholder(
            name="Senate Appropriations - MILCON-VA Subcommittee",
            role="Funding Authority",
            why_they_care="Controls VA discretionary spending",
            priority=Likelihood.HIGH,
        ),
        Stakeholder(
            name="Office of Management and Budget",
            role="Executive Budget",
            why_they_care="Shapes administration budget requests",
            priority=Likelihood.MEDIUM,
        ),
    ],
    IssueArea.OVERSIGHT: [
        Stakeholder(
            name="VA Office of Inspector General",
            role="Internal Watchdog",
            why_they_care="Investigates waste, fraud, abuse; issues reports",
            priority=Likelihood.HIGH,
        ),
        Stakeholder(
            name="Government Accountability Office",
            role="Congressional Watchdog",
            why_they_care="Audits VA programs; informs Congress",
            priority=Likelihood.HIGH,
        ),
        Stakeholder(
            name="House Oversight Committee",
            role="Congressional Oversight",
            why_they_care="Broad oversight authority; investigative powers",
            priority=Likelihood.MEDIUM,
        ),
    ],
}

# Common objections by issue area
OBJECTION_TEMPLATES = {
    IssueArea.BENEFITS_CLAIMS: [
        ObjectionResponse(
            objection="Isn't the claims backlog getting better?",
            response="The backlog numbers don't tell the full story. While pending claims may decrease, rework rates and appeal volumes indicate systemic issues that require addressing root causes, not just speeding up initial decisions.",
        ),
        ObjectionResponse(
            objection="Why should we prioritize veterans' claims over other programs?",
            response="Veterans earned these benefits through service. Timely claims processing isn't charity - it's fulfilling a contractual obligation. Delays cost lives: veterans waiting for healthcare decisions often forego needed treatment.",
        ),
        ObjectionResponse(
            objection="Isn't this just about increasing costs?",
            response="Efficient claims processing actually reduces costs. Appeals, rework, and litigation from bad initial decisions are far more expensive than getting it right the first time. Investing in quality saves money.",
        ),
    ],
    IssueArea.ACCREDITATION: [
        ObjectionResponse(
            objection="Why do veterans need representatives - can't they file claims themselves?",
            response="The VA claims system is extraordinarily complex. Veterans with representation have significantly higher approval rates and faster processing. Accreditation ensures quality representation.",
        ),
        ObjectionResponse(
            objection="Aren't attorneys just extracting fees from veterans?",
            response="Attorney fees are capped and regulated by VA. Attorneys only collect fees from past-due benefits - veterans never pay out of pocket. The real question is access to quality representation.",
        ),
    ],
    IssueArea.APPROPRIATIONS: [
        ObjectionResponse(
            objection="The VA budget is already enormous - why increase it?",
            response="VA's budget reflects growing demand from aging veterans and new PACT Act beneficiaries. The question isn't whether to spend, but whether to spend on proactive care or reactive crisis management.",
        ),
    ],
}


def _delta_to_citation(delta: AggregatedDelta) -> SourceCitation:
    """Convert an AggregatedDelta to a SourceCitation."""
    return SourceCitation(
        source_type=delta.source_type,
        source_id=delta.source_id,
        title=delta.title[:100] + "..." if len(delta.title) > 100 else delta.title,
        url=delta.url,
        date=delta.published_date,
        excerpt=delta.summary[:200] if delta.summary else None,
    )


def _draft_message_from_delta(delta: AggregatedDelta, index: int) -> Message:
    """
    Draft a talking point message from a high-impact delta.

    Creates speakable language the CEO can actually deliver.
    """
    # Extract key facts
    title = delta.title
    source_type = delta.source_type.value.replace("_", " ").title()

    # Generate speakable message based on content type
    if delta.source_type == SourceType.FEDERAL_REGISTER:
        if "final rule" in title.lower():
            text = f"VA just finalized new regulations on {_extract_topic(title)}. We need to assess how this affects our operations and advise affected veterans within 30 days."
        elif "proposed rule" in title.lower():
            text = f"VA is proposing changes to {_extract_topic(title)}. We have a window to submit comments and shape the final rule."
        else:
            text = (
                f"A new Federal Register notice on {_extract_topic(title)} requires our attention."
            )
    elif delta.source_type == SourceType.BILL:
        action = delta.metadata.get("latest_action_text", "")
        if "passed" in action.lower():
            text = f"Congress passed legislation on {_extract_topic(title)}. We need to prepare for implementation or engage on the companion bill."
        elif "hearing" in action.lower():
            text = f"Congress is holding hearings on {_extract_topic(title)}. We should submit testimony or prepare backgrounders for key members."
        else:
            text = f"New legislation introduced on {_extract_topic(title)} would impact veteran benefits. We should track and engage early."
    elif delta.source_type == SourceType.HEARING:
        hearing_date = delta.metadata.get("hearing_date", "soon")
        text = f"A congressional hearing on {_extract_topic(title)} is scheduled for {hearing_date}. We should identify witnesses and prepare materials."
    elif delta.source_type == SourceType.OVERSIGHT:
        if delta.metadata.get("is_escalation"):
            text = f"A critical oversight report on {_extract_topic(title)} requires immediate response. We should review findings and prepare our position."
        else:
            text = f"New oversight activity on {_extract_topic(title)}. We should monitor and prepare if needed."
    else:
        text = f"A development in {_extract_topic(title)} requires CEO attention."

    context = delta.summary or f"Source: {source_type} - {delta.source_id}"

    return Message(
        text=text,
        context=context[:500] if context else "",
        supporting_citations=[_delta_to_citation(delta)],
    )


def _extract_topic(title: str) -> str:
    """Extract the core topic from a title for speakable messages."""
    # Remove common prefixes
    prefixes = [
        "Veterans Benefits Administration",
        "Department of Veterans Affairs",
        "VA",
        "To amend title 38",
        "A bill to",
        "Relating to",
    ]
    clean = title
    for prefix in prefixes:
        if clean.lower().startswith(prefix.lower()):
            clean = clean[len(prefix) :].strip(" -:,")

    # Truncate for readability
    if len(clean) > 60:
        # Find a natural break point
        for sep in [",", ";", " - ", " — "]:
            if sep in clean[:60]:
                clean = clean[: clean.index(sep)]
                break
        else:
            clean = clean[:57] + "..."

    return clean


def _draft_ask_from_delta(delta: AggregatedDelta) -> AskItem | None:
    """Generate a specific ask based on delta content."""
    if delta.source_type == SourceType.FEDERAL_REGISTER:
        if "proposed rule" in delta.title.lower():
            return AskItem(
                action="Draft and submit public comments",
                target="Federal Register / VA regulatory office",
                rationale=f"Comment period open on {delta.title[:50]}...",
                priority=Likelihood.HIGH,
            )
        if "final rule" in delta.title.lower():
            return AskItem(
                action="Brief operations team on regulatory change",
                target="Internal operations leadership",
                rationale="New regulations require compliance review",
                priority=Likelihood.MEDIUM,
            )

    if delta.source_type == SourceType.BILL:
        action = delta.metadata.get("latest_action_text", "").lower()
        if "hearing" in action or delta.metadata.get("hearing_date"):
            return AskItem(
                action="Prepare testimony or submit statement for record",
                target=delta.metadata.get("committee_name", "Committee"),
                rationale=f"Hearing on {delta.title[:40]}...",
                priority=Likelihood.HIGH,
            )
        if "introduced" in action:
            return AskItem(
                action="Schedule meeting with bill sponsor's office",
                target=delta.metadata.get("sponsor_name", "Bill sponsor"),
                rationale="Early engagement on new legislation",
                priority=Likelihood.MEDIUM,
            )

    if delta.source_type == SourceType.HEARING:
        return AskItem(
            action="Submit written testimony or statement for the record",
            target=delta.metadata.get("committee_name", "Committee"),
            deadline=date.fromisoformat(delta.metadata.get("hearing_date", str(date.today()))[:10])
            if delta.metadata.get("hearing_date")
            else None,
            rationale=f"Hearing: {delta.title[:40]}...",
            priority=Likelihood.HIGH,
        )

    if delta.source_type == SourceType.OVERSIGHT and delta.metadata.get("is_escalation"):
        return AskItem(
            action="Prepare response to oversight findings",
            target="VA Office of Inspector General / GAO",
            rationale=f"Critical report: {delta.title[:40]}...",
            priority=Likelihood.HIGH,
        )

    return None


def _draft_risk_from_delta(delta: AggregatedDelta) -> RiskOpportunity | None:
    """Generate risk/opportunity assessment from delta."""
    is_risk = True
    description = ""

    # Determine if risk or opportunity
    title_lower = delta.title.lower()
    if any(w in title_lower for w in ["benefit", "expand", "increase", "support", "improve"]):
        is_risk = False

    if delta.source_type == SourceType.FEDERAL_REGISTER:
        if "final rule" in title_lower:
            is_risk = True
            description = (
                f"New regulation may impose compliance requirements: {_extract_topic(delta.title)}"
            )
        elif "proposed rule" in title_lower:
            is_risk = False
            description = (
                f"Opportunity to influence proposed regulation: {_extract_topic(delta.title)}"
            )
        else:
            return None

    elif delta.source_type == SourceType.BILL:
        action = delta.metadata.get("latest_action_text", "").lower()
        if "passed" in action:
            description = (
                f"Passed legislation may require operational changes: {_extract_topic(delta.title)}"
            )
            is_risk = True
        else:
            description = f"Pending legislation to monitor: {_extract_topic(delta.title)}"
            is_risk = delta.impact_score > 0.6

    elif delta.source_type == SourceType.OVERSIGHT:
        if delta.metadata.get("is_escalation"):
            description = f"Oversight finding requires response: {_extract_topic(delta.title)}"
            is_risk = True
        else:
            return None

    else:
        return None

    if not description:
        return None

    # Determine likelihood and impact from scores
    likelihood = Likelihood.LOW
    if delta.impact_score > 0.7:
        likelihood = Likelihood.HIGH
    elif delta.impact_score > 0.4:
        likelihood = Likelihood.MEDIUM

    impact = Likelihood.LOW
    if delta.relevance_score > 0.7:
        impact = Likelihood.HIGH
    elif delta.relevance_score > 0.4:
        impact = Likelihood.MEDIUM

    return RiskOpportunity(
        description=description,
        is_risk=is_risk,
        likelihood=likelihood,
        impact=impact,
        supporting_citations=[_delta_to_citation(delta)],
    )


def _draft_snapshot_from_delta(delta: AggregatedDelta) -> IssueSnapshot | None:
    """Generate issue snapshot for high-impact deltas."""
    # Only create snapshots for actionable items
    if delta.impact_score < 0.5:
        return None

    policy_hook = ""
    what_it_does = ""
    why_it_matters = ""
    line_we_want = ""
    is_insert = True

    if delta.source_type == SourceType.FEDERAL_REGISTER:
        policy_hook = f"FR Doc {delta.source_id}"
        what_it_does = delta.summary or f"Federal Register action on {_extract_topic(delta.title)}"
        why_it_matters = "May affect veteran benefits processing and our operational procedures."
        if "proposed rule" in delta.title.lower():
            line_we_want = "Submit comments preserving current practices and veteran access."
        else:
            line_we_want = "Review compliance requirements and prepare implementation plan."

    elif delta.source_type == SourceType.BILL:
        bill_id = delta.source_id
        policy_hook = f"{bill_id} - {_extract_topic(delta.title)[:30]}"
        what_it_does = (
            delta.metadata.get("latest_action_text") or "Congressional action on veterans policy"
        )
        why_it_matters = "Direct impact on veteran benefits and claims processing."
        line_we_want = "Support language that streamlines claims and expands access."

    elif delta.source_type == SourceType.HEARING:
        policy_hook = f"Hearing: {delta.metadata.get('committee_name', 'Committee')}"
        what_it_does = delta.title
        why_it_matters = (
            "Congressional oversight attention on this topic signals potential legislative action."
        )
        line_we_want = "Prepare testimony supporting veteran access to benefits."

    else:
        return None

    if not policy_hook:
        return None

    return IssueSnapshot(
        issue_area=delta.issue_area,
        policy_hook=policy_hook,
        what_it_does=what_it_does[:300],
        why_it_matters=why_it_matters[:300],
        line_we_want=line_we_want[:300],
        is_insert=is_insert,
        supporting_citations=[_delta_to_citation(delta)],
    )


def analyze_deltas(aggregation: AggregationResult) -> AnalysisResult:
    """
    Analyze aggregated deltas and produce draft brief content.

    This is the core analyst function that:
    1. Identifies top issues
    2. Drafts talking points
    3. Maps stakeholders
    4. Generates risks/opportunities
    5. Creates ask list
    6. Drafts issue snapshots
    7. Prepares objection responses
    """
    # Get top deltas by combined score
    top_deltas = get_top_deltas(aggregation, limit=10)

    # Identify top 5 issues for CEO attention
    top_issues = top_deltas[:5]

    # Draft 3 messages from top 3 issues
    draft_messages = []
    for i, delta in enumerate(top_issues[:3]):
        msg = _draft_message_from_delta(delta, i)
        draft_messages.append(msg)

    # Ensure we have exactly 3 messages
    while len(draft_messages) < 3:
        draft_messages.append(
            Message(
                text="Continue monitoring policy developments for emerging issues.",
                context="No high-priority items identified in this category.",
            )
        )

    # Map stakeholders based on top issue areas
    draft_stakeholders = []
    seen_stakeholders = set()
    top_issue_areas = list({d.issue_area for d in top_issues[:5]})

    for area in top_issue_areas:
        for s in STAKEHOLDER_TEMPLATES.get(area, []):
            if s.name not in seen_stakeholders:
                draft_stakeholders.append(s)
                seen_stakeholders.add(s.name)
            if len(draft_stakeholders) >= 10:
                break
        if len(draft_stakeholders) >= 10:
            break

    # Add generic stakeholders if needed
    generic_stakeholders = [
        Stakeholder(
            name="VA Secretary's Office",
            role="VA Leadership",
            why_they_care="Overall VA policy direction",
            priority=Likelihood.HIGH,
        ),
        Stakeholder(
            name="White House Domestic Policy Council",
            role="Executive Branch",
            why_they_care="Veterans policy is administration priority",
            priority=Likelihood.MEDIUM,
        ),
    ]
    for s in generic_stakeholders:
        if s.name not in seen_stakeholders and len(draft_stakeholders) < 5:
            draft_stakeholders.append(s)

    # Generate risks/opportunities
    draft_risks_opps = []
    for delta in top_deltas[:7]:
        risk_opp = _draft_risk_from_delta(delta)
        if risk_opp:
            draft_risks_opps.append(risk_opp)

    # Generate ask list
    draft_asks = []
    for delta in top_deltas[:10]:
        ask = _draft_ask_from_delta(delta)
        if ask and len(draft_asks) < 7:
            draft_asks.append(ask)

    # Ensure minimum 3 asks
    if len(draft_asks) < 3:
        draft_asks.append(
            AskItem(
                action="Review weekly intelligence summary with leadership",
                target="Executive leadership team",
                rationale="Maintain situational awareness on policy environment",
                priority=Likelihood.LOW,
            )
        )

    # Generate issue snapshots (max 3)
    draft_snapshots = []
    for delta in top_deltas[:5]:
        snapshot = _draft_snapshot_from_delta(delta)
        if snapshot and len(draft_snapshots) < 3:
            draft_snapshots.append(snapshot)

    # Get objection responses based on top issue areas
    draft_objections = []
    for area in top_issue_areas[:2]:
        for obj in OBJECTION_TEMPLATES.get(area, []):
            if len(draft_objections) < 3:
                draft_objections.append(obj)

    # Ensure minimum 3 objections
    while len(draft_objections) < 3:
        draft_objections.append(
            ObjectionResponse(
                objection="Why should we focus on this now?",
                response="Policy windows close quickly. Early engagement positions us to shape outcomes rather than react to them. The cost of inaction is loss of influence.",
            )
        )

    return AnalysisResult(
        top_issues=top_issues,
        draft_messages=draft_messages,
        draft_stakeholders=draft_stakeholders,
        draft_risks_opps=draft_risks_opps,
        draft_asks=draft_asks,
        draft_snapshots=draft_snapshots,
        draft_objections=draft_objections,
        analyzed_at=datetime.utcnow(),
        total_deltas_reviewed=aggregation.total_count,
        issues_identified=len(top_issues),
    )
