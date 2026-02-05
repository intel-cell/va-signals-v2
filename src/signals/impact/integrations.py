"""CHARLIE COMMAND - Phase 5: Inter-Command Integration.

Integration interfaces for:
- DELTA COMMAND: Push heat scores to battlefield dashboard
- ALPHA COMMAND: Provide impact content for CEO Brief
- BRAVO COMMAND: Enrich impact memos with evidence pack citations

Per FRAGO 001/002 schema coordination protocol.
"""

import json
from datetime import datetime, timezone
from typing import Optional

from ...db import connect, execute, table_exists

from .models import (
    HeatMap,
    HeatMapIssue,
    HeatMapQuadrant,
    ImpactMemo,
    Objection,
    RiskLevel,
    Posture,
    IssueArea,
)
from .db import (
    get_impact_memos,
    get_high_priority_issues,
    get_latest_heat_map,
    get_objections,
)
from .heat_map_generator import render_heat_map_for_brief, get_current_heat_map
from .objection_library import render_objection_for_brief


# =============================================================================
# DELTA COMMAND INTEGRATION - Heat Scores to Battlefield Dashboard
# =============================================================================

def push_heat_scores_to_delta(heat_map: HeatMap) -> dict:
    """Push heat scores from CHARLIE heat map to DELTA battlefield vehicles.

    Per SCHEMA_DELTA_battlefield_dashboard.md:
    - Updates bf_vehicles.heat_score for matching vehicle_id
    - vehicle_id format: "bill_hr-119-XXXX", "fr_FR-YYYY-MM-DD", etc.

    Args:
        heat_map: HeatMap object with scored issues

    Returns:
        Dict with {updated: int, not_found: int, errors: list}
    """
    con = connect()

    # Check if DELTA tables exist
    if not table_exists(con, "bf_vehicles"):
        con.close()
        return {
            "updated": 0,
            "not_found": 0,
            "errors": ["bf_vehicles table not found - DELTA not initialized"],
        }

    updated = 0
    not_found = 0
    errors = []

    for issue in heat_map.issues:
        try:
            # Convert CHARLIE issue_id to DELTA vehicle_id format
            vehicle_id = _issue_id_to_vehicle_id(issue.issue_id)

            # Update heat score in bf_vehicles
            cur = execute(
                con,
                """UPDATE bf_vehicles
                   SET heat_score = :heat_score, updated_at = :updated_at
                   WHERE vehicle_id = :vehicle_id""",
                {
                    "vehicle_id": vehicle_id,
                    "heat_score": issue.score,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )

            if cur.rowcount > 0:
                updated += 1
            else:
                not_found += 1

        except Exception as e:
            errors.append(f"Error updating {issue.issue_id}: {str(e)}")

    con.commit()
    con.close()

    return {
        "updated": updated,
        "not_found": not_found,
        "errors": errors,
        "heat_map_id": heat_map.heat_map_id,
    }


def batch_push_heat_scores(scores: list[dict]) -> dict:
    """Push batch of heat scores to DELTA.

    Per SCHEMA_DELTA Section 3.1:
    Input: [{"vehicle_id": "...", "heat_score": 85.5}, ...]

    Args:
        scores: List of dicts with vehicle_id and heat_score

    Returns:
        Dict with {updated: int, not_found: int, errors: list}
    """
    con = connect()

    if not table_exists(con, "bf_vehicles"):
        con.close()
        return {
            "updated": 0,
            "not_found": 0,
            "errors": ["bf_vehicles table not found - DELTA not initialized"],
        }

    updated = 0
    not_found = 0
    errors = []
    now = datetime.now(timezone.utc).isoformat()

    for score_entry in scores:
        try:
            vehicle_id = score_entry.get("vehicle_id")
            heat_score = score_entry.get("heat_score")

            if not vehicle_id or heat_score is None:
                errors.append(f"Invalid entry: {score_entry}")
                continue

            cur = execute(
                con,
                """UPDATE bf_vehicles
                   SET heat_score = :heat_score, updated_at = :updated_at
                   WHERE vehicle_id = :vehicle_id""",
                {
                    "vehicle_id": vehicle_id,
                    "heat_score": float(heat_score),
                    "updated_at": now,
                },
            )

            if cur.rowcount > 0:
                updated += 1
            else:
                not_found += 1

        except Exception as e:
            errors.append(f"Error updating {score_entry}: {str(e)}")

    con.commit()
    con.close()

    return {
        "updated": updated,
        "not_found": not_found,
        "errors": errors,
    }


def get_vehicles_needing_heat_scores(limit: int = 100) -> list[dict]:
    """Get DELTA vehicles that don't have heat scores yet.

    Per SCHEMA_DELTA Section 3.1:
    Returns vehicles for CHARLIE to process.
    """
    con = connect()

    if not table_exists(con, "bf_vehicles"):
        con.close()
        return []

    cur = execute(
        con,
        """SELECT vehicle_id, vehicle_type, title, identifier, current_stage
           FROM bf_vehicles
           WHERE heat_score IS NULL
           ORDER BY created_at DESC
           LIMIT :limit""",
        {"limit": limit},
    )

    rows = cur.fetchall()
    con.close()

    return [
        {
            "vehicle_id": r[0],
            "vehicle_type": r[1],
            "title": r[2],
            "identifier": r[3],
            "current_stage": r[4],
        }
        for r in rows
    ]


def _issue_id_to_vehicle_id(issue_id: str) -> str:
    """Convert CHARLIE issue_id to DELTA vehicle_id format.

    CHARLIE formats: "BILL-hr-119-1234", "HEARING-118920", "FR-2026-01234"
    DELTA formats: "bill_hr-119-1234", "hearing_118920", "fr_FR-2026-01234"
    """
    if issue_id.startswith("BILL-"):
        return f"bill_{issue_id[5:]}"
    elif issue_id.startswith("HEARING-"):
        return f"hearing_{issue_id[8:]}"
    elif issue_id.startswith("FR-"):
        return f"fr_{issue_id}"
    elif issue_id.startswith("MEMO-"):
        # Memos don't directly map to vehicles
        return issue_id
    else:
        return issue_id.lower().replace("-", "_")


# =============================================================================
# ALPHA COMMAND INTEGRATION - Impact Content for CEO Brief
# =============================================================================

def get_impact_section_for_brief(limit: int = 5) -> dict:
    """Get impact data formatted for ALPHA CEO Brief.

    Per SCHEMA_ALPHA Section 3:
    Returns content for risks_opportunities and objections_responses sections.

    Returns:
        Dict with:
        - risks_opportunities: list[dict] matching RiskOpportunity schema
        - objections_responses: list[dict] matching ObjectionResponse schema
        - heat_map_text: str rendered heat map
    """
    # Get high priority issues for risks/opportunities
    high_priority = get_high_priority_issues(limit=limit)

    risks_opportunities = []
    for issue in high_priority:
        # Determine if risk or opportunity based on posture
        memo = _get_memo_for_issue(issue.get("issue_id"))
        is_risk = True  # Default to risk

        if memo:
            posture = memo.get("our_posture", "monitor")
            is_risk = posture in ("oppose", "monitor")

        # Map CHARLIE score to ALPHA likelihood/impact
        likelihood = _score_to_likelihood(issue.get("likelihood", 3))
        impact = _score_to_impact(issue.get("impact", 3))

        ro = {
            "description": issue.get("title", ""),
            "is_risk": is_risk,
            "likelihood": likelihood,
            "impact": impact,
            "mitigation_or_action": memo.get("recommended_action") if memo else None,
            "supporting_citations": memo.get("sources", []) if memo else [],
        }
        risks_opportunities.append(ro)

    # Get objections for CEO Brief
    objections = get_objections(limit=5)
    objections_responses = [
        {
            "objection": obj["objection_text"],
            "response": obj["response_text"],
            "supporting_citations": obj.get("supporting_evidence", []),
        }
        for obj in objections
    ]

    # Get heat map text
    heat_map = get_current_heat_map()
    heat_map_text = render_heat_map_for_brief(heat_map) if heat_map else ""

    return {
        "risks_opportunities": risks_opportunities,
        "objections_responses": objections_responses,
        "heat_map_text": heat_map_text,
    }


def get_risks_for_brief(limit: int = 5) -> list[dict]:
    """Get risk/opportunity items formatted for ALPHA CEO Brief.

    Per SCHEMA_ALPHA RiskOpportunity model:
    - description: str
    - is_risk: bool
    - likelihood: "high"|"medium"|"low"
    - impact: "high"|"medium"|"low"
    - mitigation_or_action: Optional[str]
    - supporting_citations: list[SourceCitation]
    """
    high_priority = get_high_priority_issues(limit=limit)

    risks = []
    for issue in high_priority:
        memo = _get_memo_for_issue(issue.get("issue_id"))

        risk = {
            "description": issue.get("title", ""),
            "is_risk": True,
            "likelihood": _score_to_likelihood(issue.get("likelihood", 3)),
            "impact": _score_to_impact(issue.get("impact", 3)),
            "mitigation_or_action": memo.get("recommended_action") if memo else None,
            "supporting_citations": _format_citations_for_alpha(memo) if memo else [],
        }
        risks.append(risk)

    return risks


def get_objections_for_brief(limit: int = 3) -> list[dict]:
    """Get objection/response pairs formatted for ALPHA CEO Brief.

    Per SCHEMA_ALPHA ObjectionResponse model:
    - objection: str
    - response: str
    - supporting_citations: list[SourceCitation]
    """
    objections = get_objections(limit=limit)

    return [
        {
            "objection": obj["objection_text"],
            "response": obj["response_text"],
            "supporting_citations": [
                {"source_type": "authority_doc", "source_id": ev, "title": ev, "url": "", "date": ""}
                for ev in obj.get("supporting_evidence", [])
            ],
        }
        for obj in objections
    ]


def _get_memo_for_issue(issue_id: str) -> Optional[dict]:
    """Get impact memo for an issue."""
    from .db import get_memos_by_issue

    memos = get_memos_by_issue(issue_id)
    return memos[0] if memos else None


def _score_to_likelihood(score: int) -> str:
    """Convert 1-5 score to ALPHA likelihood enum."""
    if score >= 4:
        return "high"
    elif score >= 2:
        return "medium"
    else:
        return "low"


def _score_to_impact(score: int) -> str:
    """Convert 1-5 score to ALPHA impact enum."""
    if score >= 4:
        return "high"
    elif score >= 2:
        return "medium"
    else:
        return "low"


def _format_citations_for_alpha(memo: dict) -> list[dict]:
    """Format memo sources as ALPHA SourceCitation objects."""
    if not memo:
        return []

    policy_hook = memo.get("policy_hook", {})

    # Create citation from policy hook
    citation = {
        "source_type": _vehicle_type_to_source_type(policy_hook.get("vehicle_type", "")),
        "source_id": policy_hook.get("vehicle", ""),
        "title": memo.get("what_it_does", "")[:100],
        "url": policy_hook.get("source_url", ""),
        "date": policy_hook.get("effective_date", ""),
    }

    return [citation]


def _vehicle_type_to_source_type(vehicle_type: str) -> str:
    """Map CHARLIE vehicle_type to ALPHA SourceType."""
    mapping = {
        "bill": "bill",
        "rule": "federal_register",
        "hearing": "hearing",
        "report": "gao",
        "executive_order": "federal_register",
    }
    return mapping.get(vehicle_type, "federal_register")


# =============================================================================
# BRAVO COMMAND INTEGRATION - Evidence Pack Enrichment
# =============================================================================

def enrich_memo_with_evidence(memo_id: str, issue_id: str) -> Optional[dict]:
    """Enrich an impact memo with BRAVO evidence pack.

    Per SCHEMA_BRAVO Section 3.2:
    - Calls get_evidence_pack_by_issue(issue_id)
    - Returns enriched memo with citations

    Args:
        memo_id: CHARLIE memo ID
        issue_id: Issue ID to search for evidence

    Returns:
        Dict with evidence citations if found, None otherwise
    """
    con = connect()

    # Check if BRAVO tables exist
    if not table_exists(con, "evidence_packs"):
        con.close()
        return None

    # Find evidence pack for issue
    cur = execute(
        con,
        """SELECT pack_id, title, summary, status
           FROM evidence_packs
           WHERE issue_id = :issue_id AND status = 'validated'
           ORDER BY generated_at DESC LIMIT 1""",
        {"issue_id": issue_id},
    )

    pack_row = cur.fetchone()
    if not pack_row:
        con.close()
        return None

    pack_id = pack_row[0]

    # Get claims for this pack
    cur = execute(
        con,
        """SELECT claim_id, claim_text, claim_type, confidence
           FROM evidence_claims
           WHERE pack_id = :pack_id""",
        {"pack_id": pack_id},
    )
    claims = cur.fetchall()

    # Get sources for claims
    sources = []
    for claim in claims:
        claim_id = claim[0]
        cur = execute(
            con,
            """SELECT es.source_id, es.source_type, es.title, es.url, es.date_published
               FROM evidence_claim_sources ecs
               JOIN evidence_sources es ON ecs.source_id = es.source_id
               WHERE ecs.claim_id = :claim_id""",
            {"claim_id": claim_id},
        )
        for src in cur.fetchall():
            sources.append({
                "source_id": src[0],
                "source_type": src[1],
                "title": src[2],
                "url": src[3],
                "date": src[4],
            })

    con.close()

    return {
        "pack_id": pack_id,
        "pack_title": pack_row[1],
        "summary": pack_row[2],
        "claims_count": len(claims),
        "sources": sources,
    }


def find_evidence_for_source(source_type: str, source_id: str) -> Optional[dict]:
    """Find evidence pack citation for a source.

    Per SCHEMA_ALPHA Section 3 (BRAVO Integration Interface):
    Searches evidence_sources table for matching source.

    Args:
        source_type: Type (federal_register, bill, gao_report, etc.)
        source_id: Source identifier

    Returns:
        Citation data for enrichment, or None
    """
    con = connect()

    if not table_exists(con, "evidence_sources"):
        con.close()
        return None

    cur = execute(
        con,
        """SELECT source_id, source_type, title, url, date_published, date_accessed,
                  fr_citation, bill_number, report_number
           FROM evidence_sources
           WHERE source_type = :source_type
             AND (source_id = :source_id
                  OR fr_doc_number = :source_id
                  OR bill_number = :source_id
                  OR report_number = :source_id)
           LIMIT 1""",
        {"source_type": source_type, "source_id": source_id},
    )

    row = cur.fetchone()
    con.close()

    if not row:
        return None

    return {
        "source_id": row[0],
        "source_type": row[1],
        "title": row[2],
        "url": row[3],
        "date": row[4] or row[5],
        "fr_citation": row[6],
        "bill_number": row[7],
        "report_number": row[8],
    }


def get_citations_for_topic(topic: str, limit: int = 10) -> list[dict]:
    """Search for citations relevant to a topic.

    Per SCHEMA_BRAVO Section 3.2:
    Returns list of citation dicts with source details.

    Args:
        topic: Search keyword(s)
        limit: Maximum results

    Returns:
        List of citation dicts
    """
    con = connect()

    if not table_exists(con, "evidence_sources"):
        con.close()
        return []

    search_pattern = f"%{topic}%"
    cur = execute(
        con,
        """SELECT source_id, source_type, title, url, date_published
           FROM evidence_sources
           WHERE title LIKE :pattern
           ORDER BY date_published DESC
           LIMIT :limit""",
        {"pattern": search_pattern, "limit": limit},
    )

    rows = cur.fetchall()
    con.close()

    return [
        {
            "source_id": r[0],
            "source_type": r[1],
            "title": r[2],
            "url": r[3],
            "date": r[4],
        }
        for r in rows
    ]


# =============================================================================
# FULL INTEGRATION PIPELINE
# =============================================================================

def run_charlie_integration() -> dict:
    """Run full CHARLIE integration cycle.

    1. Generate current heat map
    2. Push heat scores to DELTA
    3. Prepare impact content for ALPHA

    Returns:
        Integration results summary
    """
    from .heat_map_generator import generate_heat_map

    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "delta_sync": None,
        "alpha_content": None,
        "errors": [],
    }

    try:
        # Generate heat map from current memos
        heat_map = generate_heat_map(save=True)

        # Push to DELTA
        delta_result = push_heat_scores_to_delta(heat_map)
        results["delta_sync"] = delta_result

        # Prepare ALPHA content
        alpha_content = get_impact_section_for_brief()
        results["alpha_content"] = {
            "risks_count": len(alpha_content.get("risks_opportunities", [])),
            "objections_count": len(alpha_content.get("objections_responses", [])),
            "heat_map_generated": bool(alpha_content.get("heat_map_text")),
        }

    except Exception as e:
        results["errors"].append(str(e))

    return results


# =============================================================================
# STATUS CHECK
# =============================================================================

def check_integration_status() -> dict:
    """Check status of all inter-command integrations.

    Returns status of DELTA and BRAVO connections.
    """
    con = connect()

    status = {
        "charlie_ready": True,
        "delta_connected": table_exists(con, "bf_vehicles"),
        "bravo_connected": table_exists(con, "evidence_packs"),
        "alpha_ready": True,  # ALPHA consumes CHARLIE output
    }

    # Check heat map availability
    heat_map = get_latest_heat_map()
    status["heat_map_available"] = heat_map is not None
    if heat_map:
        status["heat_map_id"] = heat_map.get("heat_map_id")
        status["heat_map_issues_count"] = len(heat_map.get("issues", []))

    # Check memo count
    memos = get_impact_memos(limit=1)
    status["memos_available"] = len(memos) > 0

    # Check objection count
    objections = get_objections(limit=1)
    status["objections_available"] = len(objections) > 0

    con.close()

    return status
