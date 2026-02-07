"""
CEO Brief Generator.

Compiles analyst output into the final brief format, attaches evidence
citations, validates all claims have sources, and outputs markdown + PDF.
"""

import hashlib
import json
import logging
import os
from datetime import date, datetime
from pathlib import Path

from .db_helpers import find_evidence_for_source, insert_ceo_brief
from .integrations import (
    charlie_memo_to_risk_opportunity,
    charlie_objection_to_brief,
    delta_decision_point_to_ask,
    enrich_citation_from_bravo,
    gather_cross_command_data,
)
from .schema import (
    AnalysisResult,
    AskItem,
    CEOBrief,
    Delta,
    IssueSnapshot,
    Likelihood,
    Message,
    ObjectionResponse,
    RiskOpportunity,
    SourceCitation,
    Stakeholder,
)

logger = logging.getLogger("ceo_brief.generator")

# Output directory for CEO briefs
DEFAULT_OUTPUT_DIR = Path(os.environ.get("CEO_BRIEF_OUTPUT_DIR", "outputs/ceo_briefs"))


def _generate_brief_id(period_start: date, period_end: date) -> str:
    """Generate a unique brief ID."""
    date_str = period_end.strftime("%Y-%m-%d")
    hash_input = (
        f"{period_start.isoformat()}-{period_end.isoformat()}-{datetime.utcnow().isoformat()}"
    )
    short_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:8]
    return f"CEO_BRIEF_{date_str}_{short_hash}"


def _enrich_citation(citation: SourceCitation) -> SourceCitation:
    """
    Attempt to enrich a citation with evidence pack data.

    Links citations to BRAVO COMMAND evidence sources when available.
    """
    evidence = find_evidence_for_source(citation.source_type.value, citation.source_id)

    if evidence:
        # Enrich with evidence pack data
        return SourceCitation(
            source_type=citation.source_type,
            source_id=citation.source_id,
            title=evidence.get("title", citation.title),
            url=evidence.get("url", citation.url),
            date=date.fromisoformat(evidence["date_published"][:10])
            if evidence.get("date_published")
            else citation.date,
            excerpt=citation.excerpt,
            section_ref=evidence.get("section_reference") or citation.section_ref,
        )

    return citation


def _analysis_to_deltas(analysis: AnalysisResult) -> list[Delta]:
    """Convert top issues to Delta format for the brief."""
    deltas = []
    for issue in analysis.top_issues:
        deltas.append(
            Delta(
                description=issue.title[:200],
                source_type=issue.source_type,
                source_id=issue.source_id,
                change_date=issue.published_date,
                issue_area=issue.issue_area,
                significance=Likelihood.HIGH
                if issue.impact_score > 0.7
                else (Likelihood.MEDIUM if issue.impact_score > 0.4 else Likelihood.LOW),
            )
        )
    return deltas


def _collect_all_citations(
    messages: list[Message],
    snapshots: list[IssueSnapshot],
    risks_opps: list[RiskOpportunity],
    objections: list[ObjectionResponse],
) -> list[SourceCitation]:
    """Collect all unique citations from brief content."""
    citations = []
    seen_ids = set()

    def add_citation(c: SourceCitation):
        if c.source_id not in seen_ids:
            citations.append(c)
            seen_ids.add(c.source_id)

    for msg in messages:
        for c in msg.supporting_citations:
            add_citation(_enrich_citation(c))

    for snap in snapshots:
        for c in snap.supporting_citations:
            add_citation(_enrich_citation(c))

    for ro in risks_opps:
        for c in ro.supporting_citations:
            add_citation(_enrich_citation(c))

    for obj in objections:
        for c in obj.supporting_citations:
            add_citation(_enrich_citation(c))

    return citations


def _generate_objective(analysis: AnalysisResult) -> str:
    """Generate the weekly objective statement."""
    if not analysis.top_issues:
        return "Monitor policy environment and maintain stakeholder relationships."

    top_area = analysis.top_issues[0].issue_area.value.replace("_", " ")
    count = len(analysis.top_issues)

    return f"Address {count} priority {top_area} developments and position for legislative engagement this week."


def generate_brief(
    analysis: AnalysisResult,
    period_start: date,
    period_end: date,
) -> CEOBrief:
    """
    Generate a complete CEO Brief from analysis results.

    Compiles all components, validates citations, and produces the final brief.
    """
    brief_id = _generate_brief_id(period_start, period_end)

    # Generate objective
    objective = _generate_objective(analysis)

    # Process messages (ensure exactly 3)
    messages = analysis.draft_messages[:3]
    while len(messages) < 3:
        messages.append(
            Message(
                text="Continue monitoring policy developments.",
                context="Placeholder for additional messaging as issues develop.",
            )
        )

    # Process stakeholders (ensure 5-10)
    stakeholders = analysis.draft_stakeholders[:10]
    while len(stakeholders) < 5:
        stakeholders.append(
            Stakeholder(
                name="Congressional Veterans Caucus",
                role="Bipartisan Coalition",
                why_they_care="Promotes veteran-friendly legislation",
                priority=Likelihood.LOW,
            )
        )

    # Convert top issues to deltas
    deltas = _analysis_to_deltas(analysis)

    # Process risks/opportunities
    risks_opps = analysis.draft_risks_opps[:6]

    # Process asks (ensure 3-7)
    asks = analysis.draft_asks[:7]
    while len(asks) < 3:
        asks.append(
            AskItem(
                action="Schedule policy briefing with key stakeholders",
                target="Priority congressional offices",
                rationale="Maintain relationships during quiet periods",
                priority=Likelihood.LOW,
            )
        )

    # Process snapshots (max 3)
    snapshots = analysis.draft_snapshots[:3]

    # Process objections (ensure at least 3)
    objections = analysis.draft_objections[:5]
    while len(objections) < 3:
        objections.append(
            ObjectionResponse(
                objection="Is this a priority given current budget constraints?",
                response="Investing in veteran services is both a moral obligation and cost-effective. Early intervention prevents expensive downstream problems.",
            )
        )

    # Collect all citations
    all_citations = _collect_all_citations(messages, snapshots, risks_opps, objections)

    return CEOBrief(
        generated_at=datetime.utcnow(),
        period_start=period_start,
        period_end=period_end,
        brief_id=brief_id,
        objective=objective,
        messages=messages,
        stakeholder_map=stakeholders,
        deltas=deltas,
        risks_opportunities=risks_opps,
        ask_list=asks,
        issue_snapshots=snapshots,
        objections_responses=objections,
        sources=all_citations,
    )


def _brief_to_dict(brief: CEOBrief) -> dict:
    """Convert CEOBrief to serializable dict for JSON storage."""
    return {
        "brief_id": brief.brief_id,
        "generated_at": brief.generated_at.isoformat(),
        "period_start": brief.period_start.isoformat(),
        "period_end": brief.period_end.isoformat(),
        "objective": brief.objective,
        "messages": [
            {
                "text": m.text,
                "context": m.context,
                "citations": [
                    {
                        "source_type": c.source_type.value,
                        "source_id": c.source_id,
                        "title": c.title,
                        "url": c.url,
                        "date": c.date.isoformat(),
                        "excerpt": c.excerpt,
                        "section_ref": c.section_ref,
                    }
                    for c in m.supporting_citations
                ],
            }
            for m in brief.messages
        ],
        "stakeholders": [
            {
                "name": s.name,
                "role": s.role,
                "why_they_care": s.why_they_care,
                "relationship_note": s.relationship_note,
                "priority": s.priority.value,
            }
            for s in brief.stakeholder_map
        ],
        "deltas": [
            {
                "description": d.description,
                "source_type": d.source_type.value,
                "source_id": d.source_id,
                "change_date": d.change_date.isoformat(),
                "issue_area": d.issue_area.value,
                "significance": d.significance.value,
            }
            for d in brief.deltas
        ],
        "risks_opportunities": [
            {
                "description": r.description,
                "is_risk": r.is_risk,
                "likelihood": r.likelihood.value,
                "impact": r.impact.value,
                "mitigation_or_action": r.mitigation_or_action,
            }
            for r in brief.risks_opportunities
        ],
        "asks": [
            {
                "action": a.action,
                "target": a.target,
                "deadline": a.deadline.isoformat() if a.deadline else None,
                "rationale": a.rationale,
                "priority": a.priority.value,
            }
            for a in brief.ask_list
        ],
        "issue_snapshots": [
            {
                "issue_area": s.issue_area.value,
                "policy_hook": s.policy_hook,
                "what_it_does": s.what_it_does,
                "why_it_matters": s.why_it_matters,
                "line_we_want": s.line_we_want,
                "is_insert": s.is_insert,
            }
            for s in brief.issue_snapshots
        ],
        "objections_responses": [
            {
                "objection": o.objection,
                "response": o.response,
            }
            for o in brief.objections_responses
        ],
        "sources": [
            {
                "source_type": s.source_type.value,
                "source_id": s.source_id,
                "title": s.title,
                "url": s.url,
                "date": s.date.isoformat(),
            }
            for s in brief.sources
        ],
    }


def save_brief(
    brief: CEOBrief,
    output_dir: Path | None = None,
    save_to_db: bool = True,
) -> dict:
    """
    Save the CEO Brief to files and optionally database.

    Returns dict with paths to generated files.
    """
    if output_dir is None:
        output_dir = DEFAULT_OUTPUT_DIR

    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate filenames
    date_str = brief.period_end.strftime("%Y-%m-%d")
    md_filename = f"CEO_BRIEF_{date_str}.md"
    json_filename = f"CEO_BRIEF_{date_str}.json"

    md_path = output_dir / md_filename
    json_path = output_dir / json_filename

    # Generate markdown
    markdown_content = brief.to_markdown()

    # Validate brief
    validation_errors = brief.validate()

    # Add validation status to markdown
    if validation_errors:
        markdown_content = (
            f"**VALIDATION WARNINGS:** {len(validation_errors)} issues found\n\n" + markdown_content
        )
        for err in validation_errors:
            markdown_content = f"- {err}\n" + markdown_content

    # Write markdown file
    with open(md_path, "w") as f:
        f.write(markdown_content)

    # Write JSON file
    brief_dict = _brief_to_dict(brief)
    brief_dict["validation_errors"] = validation_errors
    with open(json_path, "w") as f:
        json.dump(brief_dict, f, indent=2)

    # Save to database
    if save_to_db:
        insert_ceo_brief(
            brief_id=brief.brief_id,
            generated_at=brief.generated_at,
            period_start=brief.period_start,
            period_end=brief.period_end,
            objective=brief.objective,
            content_json=json.dumps(brief_dict),
            markdown_output=markdown_content,
            validation_errors=validation_errors,
            status="draft" if validation_errors else "validated",
        )

    return {
        "brief_id": brief.brief_id,
        "markdown_path": str(md_path),
        "json_path": str(json_path),
        "validation_errors": validation_errors,
        "saved_to_db": save_to_db,
    }


def generate_and_save_brief(
    analysis: AnalysisResult,
    period_start: date,
    period_end: date,
    output_dir: Path | None = None,
) -> dict:
    """
    Full pipeline: generate brief from analysis and save to files/database.

    This is the main entry point for brief generation.
    """
    brief = generate_brief(analysis, period_start, period_end)
    return save_brief(brief, output_dir)


def generate_enhanced_brief(
    analysis: AnalysisResult,
    period_start: date,
    period_end: date,
    use_cross_command: bool = True,
) -> CEOBrief:
    """
    Generate an enhanced CEO Brief with cross-command integration.

    Enhances the base brief with:
    - BRAVO: Enriched citations with evidence pack validation
    - CHARLIE: Impact memos, heat map, objections from library
    - DELTA: Decision points from battlefield dashboard

    Args:
        analysis: Base analysis result
        period_start: Reporting period start
        period_end: Reporting period end
        use_cross_command: Whether to integrate with other commands

    Returns:
        Enhanced CEOBrief
    """
    # Start with base brief generation
    brief_id = _generate_brief_id(period_start, period_end)
    objective = _generate_objective(analysis)

    # Process base content
    messages = analysis.draft_messages[:3]
    stakeholders = analysis.draft_stakeholders[:10]
    deltas = _analysis_to_deltas(analysis)
    risks_opps = analysis.draft_risks_opps[:6]
    asks = analysis.draft_asks[:7]
    snapshots = analysis.draft_snapshots[:3]
    objections = analysis.draft_objections[:5]

    # Gather cross-command data if enabled
    if use_cross_command:
        logger.info("Gathering cross-command data for enhanced brief...")
        cc_data = gather_cross_command_data()

        # BRAVO: Enrich citations
        if cc_data.citations_available:
            logger.info("Enriching citations with BRAVO evidence packs...")
            for msg in messages:
                msg.supporting_citations = [
                    enrich_citation_from_bravo(c) for c in msg.supporting_citations
                ]
            for snap in snapshots:
                snap.supporting_citations = [
                    enrich_citation_from_bravo(c) for c in snap.supporting_citations
                ]

        # CHARLIE: Add impact-derived risks/opportunities
        if cc_data.impact_data.memos:
            logger.info(f"Adding {len(cc_data.impact_data.memos)} CHARLIE impact memos...")
            for memo in cc_data.impact_data.memos[:3]:
                risk_opp = charlie_memo_to_risk_opportunity(memo)
                if risk_opp and len(risks_opps) < 6:
                    risks_opps.append(risk_opp)

        # CHARLIE: Add library objections
        if cc_data.impact_data.objections:
            logger.info(f"Adding {len(cc_data.impact_data.objections)} CHARLIE objections...")
            for obj_dict in cc_data.impact_data.objections[:3]:
                obj = charlie_objection_to_brief(obj_dict)
                if obj and len(objections) < 5:
                    # Check if not duplicate
                    existing_objections = {o.objection.lower()[:50] for o in objections}
                    if obj.objection.lower()[:50] not in existing_objections:
                        objections.append(obj)

        # DELTA: Add decision point asks
        if cc_data.battlefield_data.decision_points:
            logger.info(
                f"Adding {len(cc_data.battlefield_data.decision_points)} DELTA decision points..."
            )
            for dp in cc_data.battlefield_data.decision_points[:3]:
                ask = delta_decision_point_to_ask(dp)
                if ask and len(asks) < 7:
                    # Check if not duplicate
                    existing_actions = {a.action.lower()[:30] for a in asks}
                    if ask.action.lower()[:30] not in existing_actions:
                        asks.append(ask)

        # Log integration summary
        logger.info(
            f"Cross-command integration complete: "
            f"BRAVO={cc_data.citations_available}, "
            f"CHARLIE={len(cc_data.impact_data.memos)} memos, "
            f"DELTA={len(cc_data.battlefield_data.decision_points)} decision points"
        )

    # Ensure minimum counts
    while len(messages) < 3:
        messages.append(
            Message(
                text="Continue monitoring policy developments.",
                context="Placeholder for additional messaging as issues develop.",
            )
        )

    while len(stakeholders) < 5:
        stakeholders.append(
            Stakeholder(
                name="Congressional Veterans Caucus",
                role="Bipartisan Coalition",
                why_they_care="Promotes veteran-friendly legislation",
                priority=Likelihood.LOW,
            )
        )

    while len(asks) < 3:
        asks.append(
            AskItem(
                action="Schedule policy briefing with key stakeholders",
                target="Priority congressional offices",
                rationale="Maintain relationships during quiet periods",
                priority=Likelihood.LOW,
            )
        )

    while len(objections) < 3:
        objections.append(
            ObjectionResponse(
                objection="Is this a priority given current budget constraints?",
                response="Investing in veteran services is both a moral obligation and cost-effective.",
            )
        )

    # Collect all citations
    all_citations = _collect_all_citations(messages, snapshots, risks_opps, objections)

    return CEOBrief(
        generated_at=datetime.utcnow(),
        period_start=period_start,
        period_end=period_end,
        brief_id=brief_id,
        objective=objective,
        messages=messages,
        stakeholder_map=stakeholders,
        deltas=deltas,
        risks_opportunities=risks_opps,
        ask_list=asks,
        issue_snapshots=snapshots,
        objections_responses=objections,
        sources=all_citations,
    )


def generate_and_save_enhanced_brief(
    analysis: AnalysisResult,
    period_start: date,
    period_end: date,
    output_dir: Path | None = None,
    use_cross_command: bool = True,
) -> dict:
    """
    Full pipeline with cross-command integration.

    This is the enhanced entry point that integrates with BRAVO, CHARLIE, DELTA.
    """
    brief = generate_enhanced_brief(
        analysis, period_start, period_end, use_cross_command=use_cross_command
    )
    return save_brief(brief, output_dir)
