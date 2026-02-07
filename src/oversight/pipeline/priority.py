"""Escalation priority scoring for oversight events.

Pure-function module — no DB or I/O dependencies.
Combines ML score, escalation signals, severity, and source authority
into a single priority score (0.0–1.0) with action thresholds.
"""

from dataclasses import dataclass

# Source authority weights (mirrors ceo_brief/aggregator.py)
SOURCE_AUTHORITY_WEIGHTS: dict[str, float] = {
    "oig": 0.90,
    "gao": 0.85,
    "cafc": 0.80,
    "crs": 0.75,
    "bva": 0.70,
    "congressional_record": 0.70,
    "committee_press": 0.65,
    "investigative": 0.50,
    "news_wire": 0.40,
    "trade_press": 0.35,
}

SEVERITY_WEIGHTS: dict[str, float] = {
    "critical": 1.0,
    "high": 0.75,
    "medium": 0.50,
    "low": 0.25,
    "none": 0.0,
}

# Component weights when ML score is available
_W_ML = 0.30
_W_SIGNAL_COUNT = 0.25
_W_SEVERITY = 0.25
_W_SOURCE = 0.20

# Thresholds
ALERT_THRESHOLD = 0.60
WEBSOCKET_THRESHOLD = 0.40


@dataclass
class PriorityResult:
    """Result of priority scoring for an oversight event."""

    priority_score: float  # 0.0 – 1.0
    priority_level: str  # critical / high / medium / low
    component_scores: dict  # breakdown for explainability
    should_alert: bool  # True if >= ALERT_THRESHOLD
    should_push_websocket: bool  # True if >= WEBSOCKET_THRESHOLD


def _score_to_level(score: float) -> str:
    if score >= 0.80:
        return "critical"
    if score >= 0.60:
        return "high"
    if score >= 0.40:
        return "medium"
    return "low"


def compute_escalation_priority(
    event: dict,
    ml_score: float | None = None,
    escalation_signal_count: int = 0,
    escalation_severity: str = "none",
    source_type: str = "other",
) -> PriorityResult:
    """Compute a composite priority score for an oversight event.

    Args:
        event: The oversight event dict (used for metadata).
        ml_score: ML-based severity score (0–1), or None if unavailable.
        escalation_signal_count: Number of escalation signals matched.
        escalation_severity: Highest severity among matched signals.
        source_type: Primary source type key (e.g. 'gao', 'oig').

    Returns:
        PriorityResult with composite score and action flags.
    """
    # Component scores
    signal_score = min(escalation_signal_count, 5) / 5.0
    severity_score = SEVERITY_WEIGHTS.get(escalation_severity.lower(), 0.0)
    source_score = SOURCE_AUTHORITY_WEIGHTS.get(source_type.lower(), 0.30)

    components = {
        "signal_count": signal_score,
        "severity": severity_score,
        "source_authority": source_score,
    }

    if ml_score is not None:
        clamped_ml = max(0.0, min(1.0, ml_score))
        components["ml_score"] = clamped_ml
        weighted = (
            _W_ML * clamped_ml
            + _W_SIGNAL_COUNT * signal_score
            + _W_SEVERITY * severity_score
            + _W_SOURCE * source_score
        )
    else:
        # Redistribute ML weight equally across the other three components
        components["ml_score"] = None
        redistrib = _W_ML / 3.0
        weighted = (
            (_W_SIGNAL_COUNT + redistrib) * signal_score
            + (_W_SEVERITY + redistrib) * severity_score
            + (_W_SOURCE + redistrib) * source_score
        )

    # Clamp to [0, 1]
    priority_score = max(0.0, min(1.0, weighted))

    return PriorityResult(
        priority_score=round(priority_score, 4),
        priority_level=_score_to_level(priority_score),
        component_scores=components,
        should_alert=priority_score >= ALERT_THRESHOLD,
        should_push_websocket=priority_score >= WEBSOCKET_THRESHOLD,
    )
