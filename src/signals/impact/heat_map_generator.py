"""Heat Map Generator.

CHARLIE COMMAND - Phase 3: Build 2x2 risk matrix generator.

Generates visual heat maps ranking issues by:
- Likelihood (1-5): Probability of policy advancing/being enacted
- Impact (1-5): Operational/business impact if enacted
- Urgency: Days to next decision point (affects score weighting)
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from .models import (
    HeatMap,
    HeatMapIssue,
    HeatMapQuadrant,
    create_heat_map_issue,
)
from .db import (
    insert_heat_map,
    get_latest_heat_map,
    get_high_priority_issues,
    get_impact_memos,
)


# =============================================================================
# LIKELIHOOD ASSESSMENT RULES
# =============================================================================

def assess_bill_likelihood(bill: dict) -> int:
    """Assess likelihood of bill passage (1-5).

    Factors:
    - Current status (introduced < committee < floor < conference)
    - Bipartisan support (cosponsors from both parties)
    - Committee of jurisdiction match
    """
    latest_action = (bill.get("latest_action_text") or "").lower()
    cosponsors = bill.get("cosponsors_count", 0)

    score = 1  # Base: introduced

    # Status progression
    if "passed" in latest_action or "agreed to" in latest_action:
        score = 5
    elif "reported" in latest_action or "ordered to be reported" in latest_action:
        score = 4
    elif "hearing" in latest_action or "markup" in latest_action:
        score = 3
    elif "referred" in latest_action and cosponsors > 10:
        score = 2

    # Bipartisan support bonus
    if cosponsors > 50:
        score = min(5, score + 1)

    return score


def assess_rule_likelihood(rule: dict) -> int:
    """Assess likelihood of rule finalization (1-5).

    Factors:
    - Current status (NPRM < Final rule)
    - Comment period status
    - Effective date proximity
    """
    status = (rule.get("status") or rule.get("policy_current_status") or "").lower()
    effective_date = rule.get("effective_date") or rule.get("policy_effective_date")

    if "final" in status:
        return 5
    if "proposed" in status or "nprm" in status:
        return 3
    if effective_date:
        return 4

    return 2  # Default for rules


def assess_hearing_likelihood(hearing: dict) -> int:
    """Assess likelihood of hearing leading to action (1-5).

    Factors:
    - Committee (appropriations vs oversight)
    - Witness list (agency officials = higher)
    - Hearing type
    """
    title = (hearing.get("title") or "").lower()
    committee_code = (hearing.get("committee_code") or "").upper()

    score = 2  # Base for informational hearings

    # Appropriations hearings are high impact
    if "appropriation" in title:
        score = 4

    # Oversight with clear targets
    if "examining" in title or "investigation" in title:
        score = 3

    # VA committees are our primary concern
    if committee_code in ("HVAC", "SVAC"):
        score = min(5, score + 1)

    return score


def assess_generic_likelihood(memo_or_context: dict) -> int:
    """Generic likelihood assessment based on compliance exposure."""
    compliance = memo_or_context.get("compliance_exposure", "medium").lower()

    mapping = {
        "critical": 5,
        "high": 4,
        "medium": 3,
        "low": 2,
        "negligible": 1,
    }
    return mapping.get(compliance, 3)


# =============================================================================
# IMPACT ASSESSMENT RULES
# =============================================================================

def assess_bill_impact(bill: dict) -> int:
    """Assess operational impact of bill (1-5).

    Factors:
    - Title keywords
    - Policy area
    - Affected workflows count
    """
    title = (bill.get("title") or "").lower()
    policy_area = (bill.get("policy_area") or "").lower()

    score = 2  # Base

    # High impact keywords
    high_impact = ["reform", "modernization", "overhaul", "comprehensive", "major"]
    medium_impact = ["improvement", "enhancement", "amendment", "update"]

    if any(kw in title for kw in high_impact):
        score = 5
    elif any(kw in title for kw in medium_impact):
        score = 4
    elif "study" in title or "report" in title:
        score = 2

    # Veterans affairs focus
    if "veterans" in policy_area or "armed forces" in policy_area:
        score = min(5, score + 1)

    return score


def assess_rule_impact(rule: dict) -> int:
    """Assess operational impact of rule (1-5)."""
    body = (rule.get("body_text") or rule.get("what_it_does") or "").lower()

    score = 3  # Rules generally have direct impact

    if "mandatory" in body or "required" in body:
        score = 5
    elif "amend" in body or "revise" in body:
        score = 4

    return score


def assess_hearing_impact(hearing: dict) -> int:
    """Assess impact of hearing outcomes (1-5)."""
    title = (hearing.get("title") or "").lower()

    score = 2  # Base for informational

    # High scrutiny hearings
    if "investigation" in title or "audit" in title or "inspector general" in title:
        score = 4
    elif "budget" in title or "appropriation" in title:
        score = 5
    elif "oversight" in title:
        score = 3

    return score


def assess_generic_impact(memo_or_context: dict) -> int:
    """Generic impact assessment based on reputational risk and workflows."""
    reputational = memo_or_context.get("reputational_risk", "medium").lower()
    workflows = memo_or_context.get("affected_workflows", [])

    # Base on reputational risk
    mapping = {
        "critical": 5,
        "high": 4,
        "medium": 3,
        "low": 2,
        "negligible": 1,
    }
    score = mapping.get(reputational, 3)

    # Adjust for workflow count
    if len(workflows) >= 4:
        score = min(5, score + 1)

    return score


# =============================================================================
# URGENCY CALCULATION
# =============================================================================

def calculate_urgency_days(context: dict) -> int:
    """Calculate days to next decision point.

    Returns estimated days until action needed.
    """
    # Check for explicit deadlines
    effective_date = context.get("effective_date") or context.get("policy_effective_date")
    hearing_date = context.get("hearing_date")
    compliance_deadline = context.get("compliance_deadline")

    if compliance_deadline:
        try:
            deadline = datetime.fromisoformat(compliance_deadline.replace("Z", "+00:00"))
            days = (deadline - datetime.now(timezone.utc)).days
            return max(1, days)
        except (ValueError, TypeError):
            pass

    if effective_date:
        try:
            effective = datetime.fromisoformat(effective_date.replace("Z", "+00:00"))
            if isinstance(effective, datetime):
                days = (effective - datetime.now(timezone.utc)).days
                return max(1, days)
        except (ValueError, TypeError):
            pass

    if hearing_date:
        try:
            # Handle date-only string
            if "T" not in hearing_date:
                hearing = datetime.strptime(hearing_date, "%Y-%m-%d")
                hearing = hearing.replace(tzinfo=timezone.utc)
            else:
                hearing = datetime.fromisoformat(hearing_date.replace("Z", "+00:00"))
            days = (hearing - datetime.now(timezone.utc)).days
            return max(1, days)
        except (ValueError, TypeError):
            pass

    # Default urgency based on source type
    source_type = context.get("source_type", context.get("vehicle_type", ""))
    defaults = {
        "bill": 90,      # Congressional session window
        "rule": 60,      # Typical comment period
        "hearing": 14,   # Hearings are imminent
        "report": 30,    # Response window
    }
    return defaults.get(source_type, 60)


# =============================================================================
# HEAT MAP GENERATOR CLASS
# =============================================================================

class HeatMapGenerator:
    """Generates heat maps from issues/memos."""

    def generate_from_memos(self, memos: list[dict] = None) -> HeatMap:
        """Generate heat map from impact memos.

        If memos not provided, fetches from database.
        """
        if memos is None:
            memos = get_impact_memos(limit=50)

        issues = []
        for memo in memos:
            issue = self._memo_to_heat_map_issue(memo)
            issues.append(issue)

        return self._create_heat_map(issues)

    def generate_from_bills(self, bills: list[dict]) -> HeatMap:
        """Generate heat map from bill records."""
        issues = []
        for bill in bills:
            likelihood = assess_bill_likelihood(bill)
            impact = assess_bill_impact(bill)
            urgency = calculate_urgency_days(bill)

            issue = create_heat_map_issue(
                issue_id=f"BILL-{bill.get('bill_id', '')}",
                title=bill.get("title", "")[:100],
                likelihood=likelihood,
                impact=impact,
                urgency_days=urgency,
            )
            issues.append(issue)

        return self._create_heat_map(issues)

    def generate_from_hearings(self, hearings: list[dict]) -> HeatMap:
        """Generate heat map from hearing records."""
        issues = []
        for hearing in hearings:
            likelihood = assess_hearing_likelihood(hearing)
            impact = assess_hearing_impact(hearing)
            urgency = calculate_urgency_days(hearing)

            issue = create_heat_map_issue(
                issue_id=f"HEARING-{hearing.get('event_id', '')}",
                title=hearing.get("title", "")[:100],
                likelihood=likelihood,
                impact=impact,
                urgency_days=urgency,
            )
            issues.append(issue)

        return self._create_heat_map(issues)

    def generate_combined(
        self,
        bills: list[dict] = None,
        hearings: list[dict] = None,
        memos: list[dict] = None,
    ) -> HeatMap:
        """Generate combined heat map from multiple sources."""
        issues = []

        if bills:
            for bill in bills:
                likelihood = assess_bill_likelihood(bill)
                impact = assess_bill_impact(bill)
                urgency = calculate_urgency_days(bill)
                issue = create_heat_map_issue(
                    issue_id=f"BILL-{bill.get('bill_id', '')}",
                    title=bill.get("title", "")[:100],
                    likelihood=likelihood,
                    impact=impact,
                    urgency_days=urgency,
                )
                issues.append(issue)

        if hearings:
            for hearing in hearings:
                likelihood = assess_hearing_likelihood(hearing)
                impact = assess_hearing_impact(hearing)
                urgency = calculate_urgency_days(hearing)
                issue = create_heat_map_issue(
                    issue_id=f"HEARING-{hearing.get('event_id', '')}",
                    title=hearing.get("title", "")[:100],
                    likelihood=likelihood,
                    impact=impact,
                    urgency_days=urgency,
                )
                issues.append(issue)

        if memos:
            for memo in memos:
                issue = self._memo_to_heat_map_issue(memo)
                issues.append(issue)

        return self._create_heat_map(issues)

    def _memo_to_heat_map_issue(self, memo: dict) -> HeatMapIssue:
        """Convert impact memo to heat map issue."""
        why_it_matters = memo.get("why_it_matters", {})

        likelihood = assess_generic_likelihood(why_it_matters)
        impact = assess_generic_impact(why_it_matters)
        urgency = calculate_urgency_days({
            **memo.get("policy_hook", {}),
            **why_it_matters,
        })

        return create_heat_map_issue(
            issue_id=memo.get("issue_id", memo.get("memo_id", "")),
            title=memo.get("what_it_does", "")[:100] or memo.get("policy_hook", {}).get("vehicle", ""),
            likelihood=likelihood,
            impact=impact,
            urgency_days=urgency,
            memo_id=memo.get("memo_id"),
        )

    def _create_heat_map(self, issues: list[HeatMapIssue]) -> HeatMap:
        """Create heat map from issues."""
        now = datetime.now(timezone.utc)
        heat_map_id = f"HMAP-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"

        return HeatMap(
            heat_map_id=heat_map_id,
            generated_date=now.isoformat().replace("+00:00", "Z"),
            issues=issues,
        )

    def save_heat_map(self, heat_map: HeatMap) -> str:
        """Save heat map to database. Returns heat_map_id."""
        return insert_heat_map(heat_map.to_dict())


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def generate_heat_map(
    bills: list[dict] = None,
    hearings: list[dict] = None,
    memos: list[dict] = None,
    save: bool = False,
) -> HeatMap:
    """Generate heat map from available sources.

    Args:
        bills: List of bill records
        hearings: List of hearing records
        memos: List of impact memos
        save: If True, saves to database

    Returns:
        HeatMap object
    """
    generator = HeatMapGenerator()
    heat_map = generator.generate_combined(
        bills=bills,
        hearings=hearings,
        memos=memos,
    )

    if save:
        generator.save_heat_map(heat_map)

    return heat_map


def get_current_heat_map() -> Optional[HeatMap]:
    """Get the latest heat map from database."""
    data = get_latest_heat_map()
    if not data:
        return None

    issues = [
        HeatMapIssue(
            issue_id=i["issue_id"],
            title=i["title"],
            likelihood=i["likelihood"],
            impact=i["impact"],
            urgency_days=i["urgency_days"],
            score=i["score"],
            quadrant=HeatMapQuadrant(i["quadrant"]),
            memo_id=i.get("memo_id"),
        )
        for i in data.get("issues", [])
    ]

    return HeatMap(
        heat_map_id=data["heat_map_id"],
        generated_date=data["generated_date"],
        issues=issues,
    )


def render_heat_map_for_brief(heat_map: HeatMap) -> str:
    """Render heat map for CEO Brief integration.

    Returns formatted text suitable for inclusion in CEO Brief.
    """
    output = []
    output.append("## RISK HEAT MAP")
    output.append(f"Generated: {heat_map.generated_date}")
    output.append("")

    # High Priority section
    high_priority = heat_map.get_high_priority()
    if high_priority:
        output.append("### HIGH PRIORITY (Immediate Attention)")
        for issue in high_priority[:5]:
            output.append(f"- **{issue.title}** (L:{issue.likelihood} I:{issue.impact} Score:{issue.score:.1f})")
        output.append("")

    # Watch section
    watch = heat_map.get_watch_list()
    if watch:
        output.append("### WATCH (High Impact, Lower Likelihood)")
        for issue in watch[:3]:
            output.append(f"- {issue.title} (L:{issue.likelihood} I:{issue.impact})")
        output.append("")

    # Summary
    summary = heat_map.to_dict().get("summary", {})
    output.append(f"**Total Issues Tracked:** {summary.get('total_issues', len(heat_map.issues))}")

    return "\n".join(output)
