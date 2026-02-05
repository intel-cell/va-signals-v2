"""
Machine Learning module for predictive scoring and analysis.

Provides:
- Signal importance prediction
- Impact likelihood scoring
- Trend anomaly detection
- Risk classification
"""

from .scoring import SignalScorer, ScoringResult
from .features import FeatureExtractor
from .models import PredictionConfig, PredictionResult

__all__ = [
    "SignalScorer",
    "ScoringResult",
    "FeatureExtractor",
    "PredictionConfig",
    "PredictionResult",
]
