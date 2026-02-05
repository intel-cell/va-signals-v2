"""
Predictive scoring for signals.

Provides importance, impact, and urgency predictions
using rule-based and ML ensemble approaches.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Any
from dataclasses import dataclass

from .models import (
    PredictionType,
    PredictionResult,
    PredictionConfig,
    RiskLevel,
    FeatureSet,
)
from .features import FeatureExtractor

logger = logging.getLogger(__name__)


@dataclass
class ScoringResult:
    """Aggregated scoring result across all prediction types."""
    signal_id: str
    importance_score: float
    impact_score: float
    urgency_score: float
    overall_risk: RiskLevel
    overall_score: float
    confidence: float
    recommendations: list[str]
    scored_at: datetime


class SignalScorer:
    """
    Scores signals using a combination of rule-based heuristics
    and ML model predictions.

    The scoring system considers:
    - Importance: How significant is this signal?
    - Impact: What's the potential impact on veterans/operations?
    - Urgency: How soon does action need to be taken?

    These are combined into an overall risk score.
    """

    def __init__(self, config: PredictionConfig = None):
        """Initialize scorer with optional config."""
        self.config = config or PredictionConfig()
        self.feature_extractor = FeatureExtractor()

    def score(self, signal: dict[str, Any]) -> ScoringResult:
        """
        Score a signal across all dimensions.

        Args:
            signal: Signal data with title, content, dates, etc.

        Returns:
            ScoringResult with all scores and recommendations
        """
        signal_id = signal.get("signal_id", signal.get("doc_id", "unknown"))

        # Extract features
        features = self.feature_extractor.extract(signal)

        # Calculate individual scores
        importance = self._score_importance(signal, features)
        impact = self._score_impact(signal, features)
        urgency = self._score_urgency(signal, features)

        # Calculate overall score (weighted average)
        overall = (importance * 0.35) + (impact * 0.40) + (urgency * 0.25)

        # Determine risk level
        risk = self._determine_risk_level(overall)

        # Calculate confidence based on feature completeness
        confidence = self._calculate_confidence(features)

        # Generate recommendations
        recommendations = self._generate_recommendations(
            signal, features, importance, impact, urgency
        )

        return ScoringResult(
            signal_id=signal_id,
            importance_score=round(importance, 3),
            impact_score=round(impact, 3),
            urgency_score=round(urgency, 3),
            overall_risk=risk,
            overall_score=round(overall, 3),
            confidence=round(confidence, 3),
            recommendations=recommendations,
            scored_at=datetime.now(timezone.utc),
        )

    def score_importance(self, signal: dict[str, Any]) -> PredictionResult:
        """Score signal importance only."""
        features = self.feature_extractor.extract(signal)
        score = self._score_importance(signal, features)
        confidence = self._calculate_confidence(features)

        signal_id = signal.get("signal_id", signal.get("doc_id", "unknown"))

        factors = [
            {"factor": "keyword_density", "value": features.keyword_density, "weight": 0.25},
            {"factor": "source_reliability", "value": features.source_reliability_score, "weight": 0.20},
            {"factor": "complexity", "value": features.complexity_score, "weight": 0.15},
            {"factor": "entity_count", "value": min(1.0, features.entity_count / 10), "weight": 0.20},
            {"factor": "regulation_citations", "value": min(1.0, features.regulation_citations / 5), "weight": 0.20},
        ]

        explanation = self._explain_importance(score, features)

        return PredictionResult.from_score(
            prediction_type=PredictionType.IMPORTANCE,
            signal_id=signal_id,
            score=score,
            confidence=confidence,
            explanation=explanation,
            factors=factors,
            config=self.config,
        )

    def _score_importance(self, signal: dict, features: FeatureSet) -> float:
        """Calculate importance score (0-1)."""
        score = 0.0

        # Keyword density contributes up to 0.25
        score += min(0.25, features.keyword_density * 50)

        # Source reliability contributes up to 0.20
        score += features.source_reliability_score * 0.20

        # High priority keywords contribute up to 0.25
        hp_score = min(1.0, features.high_priority_keywords / 5)
        score += hp_score * 0.25

        # Complexity contributes up to 0.15
        score += features.complexity_score * 0.15

        # Entity/regulation references contribute up to 0.15
        ref_score = min(1.0, (features.entity_count + features.regulation_citations) / 10)
        score += ref_score * 0.15

        return min(1.0, score)

    def _score_impact(self, signal: dict, features: FeatureSet) -> float:
        """Calculate potential impact score (0-1)."""
        score = 0.0

        # Source reliability strongly affects impact credibility
        score += features.source_reliability_score * 0.25

        # Regulation citations indicate regulatory impact
        if features.regulation_citations > 0:
            score += min(0.25, features.regulation_citations * 0.05)

        # Specificity indicates concrete impact
        score += features.specificity_score * 0.20

        # Retroactive changes have higher impact
        if features.is_retroactive:
            score += 0.15

        # Organization mentions indicate broad scope
        org_score = min(0.15, features.organization_mentions * 0.03)
        score += org_score

        return min(1.0, score)

    def _score_urgency(self, signal: dict, features: FeatureSet) -> float:
        """Calculate urgency score (0-1)."""
        score = 0.0

        # Immediate deadline = high urgency
        if features.days_until_deadline is not None:
            if features.days_until_deadline <= 0:
                score += 0.4  # Past deadline
            elif features.days_until_deadline <= 7:
                score += 0.35
            elif features.days_until_deadline <= 30:
                score += 0.25
            elif features.days_until_deadline <= 60:
                score += 0.15
            else:
                score += 0.05

        # Effective date urgency
        if features.days_until_effective is not None:
            if features.days_until_effective <= 0:
                score += 0.3  # Already effective
            elif features.days_until_effective <= 30:
                score += 0.25
            elif features.days_until_effective <= 90:
                score += 0.15
            else:
                score += 0.05

        # Retroactive = urgent
        if features.is_retroactive:
            score += 0.2

        # No dates but high importance = moderate urgency
        if features.days_until_deadline is None and features.days_until_effective is None:
            if features.high_priority_keywords > 3:
                score += 0.2

        return min(1.0, score)

    def _determine_risk_level(self, overall_score: float) -> RiskLevel:
        """Determine risk level from overall score."""
        if overall_score >= 0.85:
            return RiskLevel.CRITICAL
        elif overall_score >= self.config.threshold_high:
            return RiskLevel.HIGH
        elif overall_score >= self.config.threshold_medium:
            return RiskLevel.MEDIUM
        elif overall_score >= self.config.threshold_low:
            return RiskLevel.LOW
        else:
            return RiskLevel.MINIMAL

    def _calculate_confidence(self, features: FeatureSet) -> float:
        """Calculate confidence based on feature completeness."""
        confidence = 0.3  # Base confidence

        # More text = more confidence
        if features.text_length > 500:
            confidence += 0.15
        elif features.text_length > 100:
            confidence += 0.10

        # Known source type
        if features.source_type in ["federal_register", "congress_gov", "va_gov"]:
            confidence += 0.20
        elif features.source_type != "other":
            confidence += 0.10

        # Has temporal data
        if features.days_until_effective is not None:
            confidence += 0.15
        if features.days_until_deadline is not None:
            confidence += 0.10

        # Has references
        if features.regulation_citations > 0:
            confidence += 0.10

        return min(1.0, confidence)

    def _generate_recommendations(
        self,
        signal: dict,
        features: FeatureSet,
        importance: float,
        impact: float,
        urgency: float
    ) -> list[str]:
        """Generate actionable recommendations based on scores."""
        recommendations = []

        # Urgency-based recommendations
        if urgency > 0.7:
            if features.days_until_deadline is not None and features.days_until_deadline <= 7:
                recommendations.append(
                    f"⚠️ URGENT: Comment deadline in {features.days_until_deadline} days. Prioritize review."
                )
            elif features.is_retroactive:
                recommendations.append(
                    "⚠️ URGENT: Retroactive changes detected. Assess immediate impact."
                )
            else:
                recommendations.append("⚠️ High urgency signal requires immediate attention.")

        # Impact-based recommendations
        if impact > 0.6:
            recommendations.append("📊 High impact potential. Brief leadership team.")
            if features.regulation_citations > 2:
                recommendations.append("📋 Multiple regulatory references. Legal review recommended.")

        # Importance-based recommendations
        if importance > 0.7:
            recommendations.append("🎯 High importance signal. Add to battlefield tracking.")

        # Source-based recommendations
        if features.source_reliability_score < 0.6:
            recommendations.append("⚡ Verify with authoritative source before action.")

        # Default recommendation
        if not recommendations:
            if importance + impact + urgency > 1.0:
                recommendations.append("📝 Monitor for developments.")
            else:
                recommendations.append("✓ Low priority. Standard monitoring sufficient.")

        return recommendations

    def _explain_importance(self, score: float, features: FeatureSet) -> str:
        """Generate human-readable explanation for importance score."""
        parts = []

        if features.source_reliability_score > 0.8:
            parts.append("authoritative source")
        if features.high_priority_keywords > 3:
            parts.append("multiple high-priority keywords")
        if features.regulation_citations > 0:
            parts.append(f"{features.regulation_citations} regulatory references")
        if features.complexity_score > 0.5:
            parts.append("high complexity")

        if not parts:
            parts.append("standard monitoring signal")

        level = "High" if score > 0.7 else "Medium" if score > 0.4 else "Low"
        return f"{level} importance due to: {', '.join(parts)}"


def score_batch(signals: list[dict], config: PredictionConfig = None) -> list[ScoringResult]:
    """Score multiple signals."""
    scorer = SignalScorer(config)
    return [scorer.score(signal) for signal in signals]
