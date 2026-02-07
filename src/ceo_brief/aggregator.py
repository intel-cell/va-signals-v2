"""
CEO Brief Aggregation Agent.

Queries all source tables for the last 7 days, identifies new/changed items,
classifies by issue area, and ranks by potential impact.
"""

import re
from datetime import date, datetime, timedelta

from .db_helpers import get_all_deltas
from .schema import AggregatedDelta, AggregationResult, IssueArea, SourceType

# Issue area classification patterns
ISSUE_PATTERNS = {
    IssueArea.BENEFITS_CLAIMS: [
        r"\bclaim[s]?\b",
        r"\bbenefit[s]?\b",
        r"\bcompensation\b",
        r"\bdisability\s+rating",
        r"\bservice[- ]connect",
        r"\bVBA\b",
        r"\bveteran[s']?\s+benefits?\b",
        r"\bpension\b",
        r"\bDIC\b",
        r"\bbacklog\b",
        r"\bappeals?\b",
        r"\bBVA\b",
        r"\bCARF\b",
    ],
    IssueArea.ACCREDITATION: [
        r"\baccredit",
        r"\bclaims?\s+agent",
        r"\bVSO\b",
        r"\battorney[s]?\b",
        r"\brepresent",
        r"\bOGC\b",
        r"\bfee[s]?\b.*\battorney",
        r"\b38\s*CFR\s*14\b",
    ],
    IssueArea.APPROPRIATIONS: [
        r"\bappropriation[s]?\b",
        r"\bbudget\b",
        r"\bfunding\b",
        r"\bfiscal\s+year\b",
        r"\b(FY|fy)\s*\d{2,4}\b",
        r"\ballocation[s]?\b",
        r"\bspending\b",
        r"\bMILCON\b",
        r"\bVA\s+budget\b",
    ],
    IssueArea.HEALTHCARE: [
        r"\bhealth\s*care\b",
        r"\bVHA\b",
        r"\bmedical\s+(center|facility|care)\b",
        r"\bCommunity\s+Care\b",
        r"\bMission\s+Act\b",
        r"\bPACT\s+Act\b",
        r"\btoxic\s+exposure\b",
        r"\bmental\s+health\b",
        r"\bwait\s+time[s]?\b",
        r"\bappointment[s]?\b",
        r"\bscheduling\b",
        r"\bhospital\b",
        r"\bphysician\b",
        r"\bnurse[s]?\b",
    ],
    IssueArea.TECHNOLOGY: [
        r"\btechnolog",
        r"\bIT\s+(system|modernization|infrastructure)\b",
        r"\belectronic\s+health\s+record",
        r"\bEHR\b",
        r"\bCerner\b",
        r"\bOracle\b",
        r"\bcybersecurity\b",
        r"\bdata\s+(breach|security)\b",
        r"\bVISTA\b",
        r"\bdigital\b",
        r"\bsoftware\b",
    ],
    IssueArea.STAFFING: [
        r"\bstaffing\b",
        r"\bhiring\b",
        r"\brecruitment\b",
        r"\bretention\b",
        r"\bvacancy\b",
        r"\bworkforce\b",
        r"\bemployee[s]?\b",
        r"\bFTE\b",
        r"\bhuman\s+(resources|capital)\b",
    ],
    IssueArea.OVERSIGHT: [
        r"\boversight\b",
        r"\bOIG\b",
        r"\binspector\s+general\b",
        r"\bGAO\b",
        r"\baudit\b",
        r"\binvestigation\b",
        r"\bwhistleblow",
        r"\baccountability\b",
        r"\bCRS\b",
        r"\breport\b.*\b(finding|recommend)\b",
    ],
    IssueArea.LEGAL: [
        r"\blegal\b",
        r"\blitigation\b",
        r"\bcourt\b",
        r"\bCAFC\b",
        r"\bCAVC\b",
        r"\bCVET\b",
        r"\bsettlement\b",
        r"\blawsuit\b",
        r"\bjudicial\b",
        r"\bruling\b",
        r"\bdecision\b.*\bcourt\b",
    ],
    IssueArea.STATE: [
        r"\bstate[- ]level\b",
        r"\bstate\s+(law|legislation|program)\b",
        r"\blocal\s+veteran",
        r"\bstate\s+VA\b",
        r"\bcounty\b.*\bveteran",
    ],
}

# Impact scoring weights
IMPACT_WEIGHTS = {
    "escalation": 0.3,  # Is this flagged as an escalation?
    "deviation": 0.15,  # Is this a deviation from baseline?
    "recency": 0.15,  # How recent is the publication date?
    "action_level": 0.25,  # What level of action (bill stage, reg type, etc.)?
    "source_authority": 0.15,  # How authoritative is the source?
}

# Action level scoring (higher = more significant)
ACTION_LEVELS = {
    # Federal Register
    "final_rule": 1.0,
    "interim_final_rule": 0.9,
    "proposed_rule": 0.7,
    "notice": 0.4,
    # Bills
    "became_law": 1.0,
    "passed_house": 0.8,
    "passed_senate": 0.8,
    "reported_committee": 0.6,
    "markup": 0.5,
    "hearing_scheduled": 0.4,
    "introduced": 0.2,
    # Oversight
    "report_release": 0.8,
    "testimony": 0.7,
    "investigation_opened": 0.9,
    "press_release": 0.5,
    # Default
    "other": 0.3,
}

# Source authority scoring
SOURCE_AUTHORITY = {
    "federal_register": 0.9,
    "bill": 0.85,
    "hearing": 0.75,
    "oversight": 0.8,
    "gao": 0.85,
    "oig": 0.9,
    "crs": 0.75,
    "state": 0.5,
    "news": 0.4,
}


def classify_issue_area(title: str, content: str | None = None) -> IssueArea:
    """
    Classify content into an issue area based on keyword patterns.

    Returns the issue area with the most matches, or OTHER if none match.
    """
    text = (title + " " + (content or "")).lower()

    scores = {}
    for area, patterns in ISSUE_PATTERNS.items():
        score = 0
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                score += 1
        if score > 0:
            scores[area] = score

    if not scores:
        return IssueArea.OTHER

    return max(scores, key=scores.get)


def _parse_action_level(delta: dict) -> str:
    """Determine action level from delta content."""
    source_type = delta.get("source_type", "")
    title = (delta.get("title") or "").lower()
    latest_action = (delta.get("latest_action_text") or "").lower()
    text = f"{title} {latest_action}"

    # Federal Register
    if source_type == "federal_register":
        if "final rule" in text:
            return "final_rule"
        if "interim final" in text:
            return "interim_final_rule"
        if "proposed rule" in text:
            return "proposed_rule"
        if "notice" in text:
            return "notice"

    # Bills
    if source_type == "bill":
        if "became public law" in text or "signed by president" in text:
            return "became_law"
        if "passed house" in text:
            return "passed_house"
        if "passed senate" in text:
            return "passed_senate"
        if "reported" in text and "committee" in text:
            return "reported_committee"
        if "markup" in text:
            return "markup"
        if "hearing" in text:
            return "hearing_scheduled"
        if "introduced" in text:
            return "introduced"

    # Oversight
    if source_type == "oversight":
        event_type = delta.get("event_type", "")
        if event_type == "report_release":
            return "report_release"
        if "testimony" in text or event_type == "testimony":
            return "testimony"
        if "investigation" in text:
            return "investigation_opened"
        if "press release" in text or event_type == "press_release":
            return "press_release"

    return "other"


def calculate_impact_score(delta: dict, period_end: date) -> float:
    """
    Calculate impact score for a delta (0-1 scale).

    Higher scores indicate more important/urgent items.
    """
    scores = {}

    # Escalation score
    is_escalation = delta.get("is_escalation", False)
    scores["escalation"] = 1.0 if is_escalation else 0.0

    # Deviation score
    is_deviation = delta.get("is_deviation", False)
    scores["deviation"] = 1.0 if is_deviation else 0.0

    # Recency score (published in last 3 days = 1.0, older = decay)
    pub_date_str = delta.get("published_date") or delta.get("first_seen_at", "")
    if pub_date_str:
        try:
            if "T" in pub_date_str:
                pub_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00")).date()
            else:
                pub_date = date.fromisoformat(pub_date_str[:10])
            days_old = (period_end - pub_date).days
            scores["recency"] = max(0.0, 1.0 - (days_old / 7.0))
        except (ValueError, TypeError):
            scores["recency"] = 0.5
    else:
        scores["recency"] = 0.5

    # Action level score
    action_level = _parse_action_level(delta)
    scores["action_level"] = ACTION_LEVELS.get(action_level, 0.3)

    # Source authority score
    source_type = delta.get("source_type", "other")
    primary_source = delta.get("primary_source_type", source_type)
    scores["source_authority"] = SOURCE_AUTHORITY.get(primary_source, 0.3)

    # Weighted average
    total = sum(scores[k] * IMPACT_WEIGHTS[k] for k in IMPACT_WEIGHTS)
    return round(total, 3)


def calculate_urgency_score(delta: dict, period_end: date) -> float:
    """
    Calculate urgency score based on deadlines and time sensitivity.

    Higher scores indicate more time-sensitive items.
    """
    score = 0.0

    # Check for comment deadlines (Federal Register)
    # This would need FR API enrichment; stub for now
    title = (delta.get("title") or "").lower()
    summary = (delta.get("summary") or "").lower()
    text = f"{title} {summary}"

    # Urgency keywords
    if any(w in text for w in ["deadline", "comment period", "effective date"]):
        score += 0.3

    if any(w in text for w in ["immediately", "urgent", "emergency", "interim"]):
        score += 0.4

    # Hearing dates
    hearing_date = delta.get("hearing_date")
    if hearing_date:
        try:
            h_date = date.fromisoformat(hearing_date[:10])
            days_until = (h_date - period_end).days
            if 0 <= days_until <= 7:
                score += 0.5
            elif days_until < 0:
                score += 0.1  # Past but recent
        except (ValueError, TypeError):
            pass

    # Bill action urgency
    latest_action = (delta.get("latest_action_text") or "").lower()
    if any(w in latest_action for w in ["passed", "signed", "veto"]):
        score += 0.4

    return min(1.0, score)


def calculate_relevance_score(delta: dict, issue_area: IssueArea) -> float:
    """
    Calculate VA claims relevance score.

    Prioritizes content directly related to VA claims processing.
    """
    # Direct claims/benefits content scores highest
    if issue_area in (IssueArea.BENEFITS_CLAIMS, IssueArea.ACCREDITATION):
        return 1.0

    # Related areas
    if issue_area in (IssueArea.LEGAL, IssueArea.OVERSIGHT):
        return 0.8

    # Indirect but relevant
    if issue_area in (IssueArea.APPROPRIATIONS, IssueArea.TECHNOLOGY, IssueArea.STAFFING):
        return 0.6

    # Healthcare (tangential to claims)
    if issue_area == IssueArea.HEALTHCARE:
        return 0.5

    # State intelligence
    if issue_area == IssueArea.STATE:
        return 0.4

    return 0.3


def _raw_to_aggregated(delta: dict, period_end: date) -> AggregatedDelta:
    """Convert a raw delta dict to an AggregatedDelta."""
    source_type_str = delta.get("source_type", "other")
    source_type_map = {
        "federal_register": SourceType.FEDERAL_REGISTER,
        "bill": SourceType.BILL,
        "hearing": SourceType.HEARING,
        "oversight": SourceType.OVERSIGHT,
        "state": SourceType.STATE,
        "gao": SourceType.GAO,
        "oig": SourceType.OIG,
        "crs": SourceType.CRS,
    }
    source_type = source_type_map.get(source_type_str, SourceType.NEWS)

    title = delta.get("title") or ""
    content = delta.get("summary") or delta.get("content") or delta.get("veteran_impact") or ""

    issue_area = classify_issue_area(title, content)

    # Parse dates
    pub_date_str = delta.get("published_date") or delta.get("pub_date") or delta.get("hearing_date")
    first_seen_str = (
        delta.get("first_seen_at") or delta.get("fetched_at") or datetime.utcnow().isoformat()
    )

    try:
        if pub_date_str and "T" in pub_date_str:
            pub_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00")).date()
        elif pub_date_str:
            pub_date = date.fromisoformat(pub_date_str[:10])
        else:
            pub_date = period_end
    except (ValueError, TypeError):
        pub_date = period_end

    try:
        first_seen = datetime.fromisoformat(first_seen_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        first_seen = datetime.utcnow()

    impact_score = calculate_impact_score(delta, period_end)
    urgency_score = calculate_urgency_score(delta, period_end)
    relevance_score = calculate_relevance_score(delta, issue_area)

    return AggregatedDelta(
        source_type=source_type,
        source_id=delta.get("source_id", ""),
        title=title,
        url=delta.get("url") or delta.get("source_url") or "",
        published_date=pub_date,
        first_seen_at=first_seen,
        issue_area=issue_area,
        raw_content=content[:5000] if content else None,  # Truncate for storage
        summary=delta.get("summary"),
        metadata=delta,  # Preserve full delta for downstream processing
        impact_score=impact_score,
        urgency_score=urgency_score,
        relevance_score=relevance_score,
    )


def aggregate_deltas(
    period_start: date | None = None,
    period_end: date | None = None,
) -> AggregationResult:
    """
    Aggregate deltas from all sources for the specified period.

    Default period is last 7 days ending today.

    Returns AggregationResult with classified and scored deltas.
    """
    if period_end is None:
        period_end = date.today()
    if period_start is None:
        period_start = period_end - timedelta(days=7)

    # Convert to datetime for queries
    since = datetime.combine(period_start, datetime.min.time())
    until = datetime.combine(period_end, datetime.max.time())

    # Fetch raw deltas
    raw = get_all_deltas(since, until)

    # Convert to AggregatedDeltas
    fr_deltas = [_raw_to_aggregated(d, period_end) for d in raw["federal_register"]]
    bill_deltas = [_raw_to_aggregated(d, period_end) for d in raw["bills"]]
    hearing_deltas = [_raw_to_aggregated(d, period_end) for d in raw["hearings"]]
    oversight_deltas = [_raw_to_aggregated(d, period_end) for d in raw["oversight"]]
    state_deltas = [_raw_to_aggregated(d, period_end) for d in raw["state"]]

    return AggregationResult(
        period_start=period_start,
        period_end=period_end,
        aggregated_at=datetime.utcnow(),
        fr_deltas=fr_deltas,
        bill_deltas=bill_deltas,
        hearing_deltas=hearing_deltas,
        oversight_deltas=oversight_deltas,
        state_deltas=state_deltas,
    )


def get_top_deltas(result: AggregationResult, limit: int = 10) -> list[AggregatedDelta]:
    """
    Get the top N deltas by combined impact, urgency, and relevance scores.
    """
    all_deltas = result.all_deltas

    # Combined score: weighted average
    def combined_score(d: AggregatedDelta) -> float:
        return (d.impact_score * 0.4) + (d.urgency_score * 0.3) + (d.relevance_score * 0.3)

    sorted_deltas = sorted(all_deltas, key=combined_score, reverse=True)
    return sorted_deltas[:limit]


def get_deltas_by_issue_area(result: AggregationResult) -> dict[IssueArea, list[AggregatedDelta]]:
    """Group deltas by issue area."""
    by_area = {area: [] for area in IssueArea}

    for delta in result.all_deltas:
        by_area[delta.issue_area].append(delta)

    # Sort each group by impact score
    for area in by_area:
        by_area[area].sort(key=lambda d: d.impact_score, reverse=True)

    return by_area
