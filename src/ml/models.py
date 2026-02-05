"""
Data models for ML predictions.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field


class PredictionType(str, Enum):
    """Types of predictions supported."""
    IMPORTANCE = "importance"  # How important is this signal?
    IMPACT = "impact"          # What's the likely impact?
    URGENCY = "urgency"        # How urgent is action needed?
    RISK = "risk"              # What's the risk level?
    ANOMALY = "anomaly"        # Is this an anomaly?


class RiskLevel(str, Enum):
    """Risk classification levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    MINIMAL = "minimal"


class PredictionConfig(BaseModel):
    """Configuration for prediction models."""
    model_config = {"protected_namespaces": ()}

    model_type: str = "gradient_boosting"  # or "random_forest", "neural_net"
    version: str = "1.0.0"
    threshold_high: float = 0.7
    threshold_medium: float = 0.4
    threshold_low: float = 0.2
    features_enabled: list[str] = Field(default_factory=lambda: [
        "text_length", "keyword_density", "source_reliability",
        "historical_impact", "temporal_urgency", "entity_count"
    ])
    use_ensemble: bool = True
    confidence_threshold: float = 0.6


class FeatureSet(BaseModel):
    """Extracted features for ML model input."""
    # Text features
    text_length: int = 0
    word_count: int = 0
    sentence_count: int = 0
    avg_word_length: float = 0.0

    # Keyword features
    keyword_matches: int = 0
    keyword_density: float = 0.0
    high_priority_keywords: int = 0

    # Source features
    source_type: str = ""
    source_reliability_score: float = 0.5
    source_historical_accuracy: float = 0.5

    # Temporal features
    days_until_effective: Optional[int] = None
    days_until_deadline: Optional[int] = None
    is_retroactive: bool = False

    # Entity features
    entity_count: int = 0
    organization_mentions: int = 0
    regulation_citations: int = 0

    # Historical features
    similar_signal_count: int = 0
    historical_impact_avg: float = 0.0
    author_track_record: float = 0.5

    # Derived features
    complexity_score: float = 0.0
    specificity_score: float = 0.0


class PredictionResult(BaseModel):
    """Result of a prediction."""
    model_config = {"protected_namespaces": ()}

    prediction_type: PredictionType
    signal_id: str
    score: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    risk_level: RiskLevel
    explanation: str
    contributing_factors: list[dict[str, Any]] = Field(default_factory=list)
    ml_model_version: str
    predicted_at: datetime
    features_used: Optional[FeatureSet] = None

    @classmethod
    def from_score(
        cls,
        prediction_type: PredictionType,
        signal_id: str,
        score: float,
        confidence: float,
        explanation: str,
        factors: list[dict] = None,
        config: PredictionConfig = None
    ) -> "PredictionResult":
        """Create prediction result from a score."""
        config = config or PredictionConfig()

        if score >= config.threshold_high:
            risk_level = RiskLevel.HIGH if score < 0.85 else RiskLevel.CRITICAL
        elif score >= config.threshold_medium:
            risk_level = RiskLevel.MEDIUM
        elif score >= config.threshold_low:
            risk_level = RiskLevel.LOW
        else:
            risk_level = RiskLevel.MINIMAL

        return cls(
            prediction_type=prediction_type,
            signal_id=signal_id,
            score=score,
            confidence=confidence,
            risk_level=risk_level,
            explanation=explanation,
            contributing_factors=factors or [],
            ml_model_version=config.version,
            predicted_at=datetime.utcnow(),
        )


class ModelMetrics(BaseModel):
    """Metrics for model evaluation."""
    model_config = {"protected_namespaces": ()}

    ml_model_name: str
    version: str
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    auc_roc: Optional[float] = None
    evaluation_date: datetime
    sample_size: int
    confusion_matrix: Optional[dict] = None


class TrainingRequest(BaseModel):
    """Request to train/retrain a model."""
    model_config = {"protected_namespaces": ()}

    ml_model_type: str
    training_data_start: str
    training_data_end: str
    validation_split: float = 0.2
    hyperparameters: Optional[dict] = None


class BatchPredictionRequest(BaseModel):
    """Request for batch predictions."""
    signal_ids: list[str]
    prediction_types: list[PredictionType] = [PredictionType.IMPORTANCE]
    include_features: bool = False
    min_confidence: float = 0.5
