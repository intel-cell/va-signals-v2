"""
Machine Learning module for predictive scoring and analysis.

Provides:
- Signal importance prediction
- Impact likelihood scoring
- Trend anomaly detection
- Risk classification
"""

from .features import FeatureExtractor
from .models import PredictionConfig, PredictionResult
from .scoring import ScoringResult, SignalScorer

__all__ = [
    "SignalScorer",
    "ScoringResult",
    "FeatureExtractor",
    "PredictionConfig",
    "PredictionResult",
]
