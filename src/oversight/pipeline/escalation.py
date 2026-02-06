"""Escalation signal checker for oversight events."""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from src.oversight.db_helpers import get_active_escalation_signals

logger = logging.getLogger(__name__)


@dataclass
class EscalationResult:
    """Result of escalation check."""

    is_escalation: bool
    matched_signals: list[str] = field(default_factory=list)
    severity: str = "none"  # critical, high, medium, none
    ml_score: Optional[float] = None
    ml_risk_level: Optional[str] = None
    ml_confidence: Optional[float] = None


def _try_ml_score(title: str, content: str) -> tuple[Optional[float], Optional[str], Optional[float]]:
    """Attempt ML scoring. Returns (score, risk_level, confidence) or (None, None, None)."""
    try:
        from src.ml import SignalScorer
        scorer = SignalScorer()
        result = scorer.score({"title": title, "content": content, "source_type": "oversight"})
        return result.overall_score, result.overall_risk.value, result.confidence
    except Exception as e:
        logger.debug("ML scoring unavailable: %s", e)
        return None, None, None


def check_escalation(title: str, content: str) -> EscalationResult:
    """
    Check if text contains escalation signals.

    Args:
        title: Event title
        content: Event content/excerpt

    Returns:
        EscalationResult with matched signals
    """
    signals = get_active_escalation_signals()

    combined_text = f"{title} {content}".lower()
    matched = []
    max_severity = "none"
    severity_order = {"critical": 3, "high": 2, "medium": 1, "none": 0}

    for signal in signals:
        pattern = signal["signal_pattern"].lower()
        signal_type = signal["signal_type"]

        # Check for match based on signal type
        if signal_type == "keyword":
            # Word boundary match for keywords
            if re.search(rf"\b{re.escape(pattern)}\b", combined_text):
                matched.append(pattern)
                if severity_order.get(signal["severity"], 0) > severity_order.get(max_severity, 0):
                    max_severity = signal["severity"]

        elif signal_type == "phrase":
            # Substring match for phrases
            if pattern in combined_text:
                matched.append(pattern)
                if severity_order.get(signal["severity"], 0) > severity_order.get(max_severity, 0):
                    max_severity = signal["severity"]

    ml_score, ml_risk_level, ml_confidence = _try_ml_score(title, content)

    return EscalationResult(
        is_escalation=len(matched) > 0,
        matched_signals=matched,
        severity=max_severity,
        ml_score=ml_score,
        ml_risk_level=ml_risk_level,
        ml_confidence=ml_confidence,
    )
