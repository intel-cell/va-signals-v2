"""
Feature extraction for ML predictions.

Extracts numerical and categorical features from signals
for use in predictive models.
"""

import re
import logging
from datetime import datetime, timezone
from typing import Optional, Any

from .models import FeatureSet

logger = logging.getLogger(__name__)

# High-priority keywords that indicate important signals
HIGH_PRIORITY_KEYWORDS = [
    "veteran", "disability", "benefit", "claim", "appeal",
    "va ", "dod", "compensation", "rating", "effective date",
    "deadline", "mandatory", "required", "final rule",
    "proposed rule", "comment period", "regulation",
    "amendment", "revision", "implementation"
]

# Keywords indicating urgency
URGENCY_KEYWORDS = [
    "immediate", "urgent", "emergency", "effective immediately",
    "within 30 days", "within 60 days", "deadline", "expires",
    "retroactive", "mandatory", "required"
]

# Source reliability scores (0-1)
SOURCE_RELIABILITY = {
    "federal_register": 0.95,
    "congress_gov": 0.95,
    "gpo": 0.90,
    "va_gov": 0.90,
    "crs": 0.85,
    "gao": 0.85,
    "state_official": 0.80,
    "news": 0.60,
    "other": 0.50,
}


class FeatureExtractor:
    """
    Extracts features from signals for ML model input.

    Handles text analysis, temporal features, source analysis,
    and historical pattern matching.
    """

    def __init__(self, db_connection=None):
        """Initialize with optional database connection for historical lookups."""
        self.db = db_connection

    def extract(self, signal: dict[str, Any]) -> FeatureSet:
        """
        Extract all features from a signal.

        Args:
            signal: Signal data dictionary with fields like:
                - title, content/body, source_type, pub_date,
                - effective_date, comments_close_date, etc.

        Returns:
            FeatureSet with all extracted features
        """
        features = FeatureSet()

        # Extract text features
        text = self._get_text(signal)
        features = self._extract_text_features(text, features)

        # Extract keyword features
        features = self._extract_keyword_features(text, features)

        # Extract source features
        features = self._extract_source_features(signal, features)

        # Extract temporal features
        features = self._extract_temporal_features(signal, features)

        # Extract entity features
        features = self._extract_entity_features(text, features)

        # Extract historical features (if DB available)
        if self.db:
            features = self._extract_historical_features(signal, features)

        # Calculate derived features
        features = self._calculate_derived_features(features)

        return features

    def _get_text(self, signal: dict) -> str:
        """Combine title and content into searchable text."""
        title = signal.get("title", "") or ""
        content = signal.get("content", "") or signal.get("body", "") or ""
        summary = signal.get("summary", "") or ""
        return f"{title} {summary} {content}".lower()

    def _extract_text_features(self, text: str, features: FeatureSet) -> FeatureSet:
        """Extract basic text statistics."""
        features.text_length = len(text)

        # Word count
        words = text.split()
        features.word_count = len(words)

        # Sentence count (rough)
        sentences = re.split(r'[.!?]+', text)
        features.sentence_count = len([s for s in sentences if s.strip()])

        # Average word length
        if words:
            features.avg_word_length = sum(len(w) for w in words) / len(words)

        return features

    def _extract_keyword_features(self, text: str, features: FeatureSet) -> FeatureSet:
        """Extract keyword-based features."""
        # Count high-priority keyword matches
        hp_matches = sum(1 for kw in HIGH_PRIORITY_KEYWORDS if kw in text)
        features.high_priority_keywords = hp_matches
        features.keyword_matches = hp_matches

        # Keyword density
        if features.word_count > 0:
            features.keyword_density = hp_matches / features.word_count

        return features

    def _extract_source_features(self, signal: dict, features: FeatureSet) -> FeatureSet:
        """Extract source-related features."""
        source_type = signal.get("source_type", "other") or "other"
        features.source_type = source_type.lower()

        # Look up reliability score
        features.source_reliability_score = SOURCE_RELIABILITY.get(
            features.source_type, 0.5
        )

        # Historical accuracy (would be calculated from past predictions)
        features.source_historical_accuracy = features.source_reliability_score

        return features

    def _extract_temporal_features(self, signal: dict, features: FeatureSet) -> FeatureSet:
        """Extract time-related features."""
        now = datetime.now(timezone.utc)

        # Days until effective date
        effective_date = signal.get("effective_date")
        if effective_date:
            try:
                eff_dt = self._parse_date(effective_date)
                if eff_dt:
                    delta = (eff_dt - now).days
                    features.days_until_effective = delta
                    features.is_retroactive = delta < 0
            except Exception:
                pass

        # Days until comment deadline
        comments_close = signal.get("comments_close_date")
        if comments_close:
            try:
                close_dt = self._parse_date(comments_close)
                if close_dt:
                    features.days_until_deadline = (close_dt - now).days
            except Exception:
                pass

        return features

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse various date formats."""
        if not date_str:
            return None

        formats = [
            "%Y-%m-%d",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%SZ",
            "%m/%d/%Y",
            "%B %d, %Y",
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str[:19], fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue

        return None

    def _extract_entity_features(self, text: str, features: FeatureSet) -> FeatureSet:
        """Extract entity-related features."""
        # Count organization mentions (simple pattern matching)
        org_patterns = [
            r'\bVA\b', r'\bDOD\b', r'\bCongress\b', r'\bSenate\b',
            r'\bHouse\b', r'\bCommittee\b', r'\bAgency\b', r'\bDepartment\b'
        ]
        org_count = sum(len(re.findall(p, text, re.IGNORECASE)) for p in org_patterns)
        features.organization_mentions = org_count

        # Count regulation citations (e.g., 38 CFR, 42 U.S.C.)
        reg_patterns = [
            r'\d+\s*CFR\s*\d+', r'\d+\s*U\.?S\.?C\.?\s*\d+',
            r'Public Law\s*\d+-\d+', r'P\.?L\.?\s*\d+-\d+'
        ]
        reg_count = sum(len(re.findall(p, text, re.IGNORECASE)) for p in reg_patterns)
        features.regulation_citations = reg_count

        # Total entity count
        features.entity_count = org_count + reg_count

        return features

    def _extract_historical_features(self, signal: dict, features: FeatureSet) -> FeatureSet:
        """Extract features based on historical data."""
        # This would query the database for similar signals
        # For now, use defaults
        features.similar_signal_count = 0
        features.historical_impact_avg = 0.5
        features.author_track_record = 0.5

        return features

    def _calculate_derived_features(self, features: FeatureSet) -> FeatureSet:
        """Calculate composite derived features."""
        # Complexity score (0-1)
        complexity = 0.0
        if features.text_length > 5000:
            complexity += 0.3
        elif features.text_length > 1000:
            complexity += 0.2
        if features.regulation_citations > 3:
            complexity += 0.3
        elif features.regulation_citations > 0:
            complexity += 0.15
        if features.avg_word_length > 6:
            complexity += 0.2
        features.complexity_score = min(1.0, complexity)

        # Specificity score (0-1)
        specificity = 0.0
        if features.entity_count > 5:
            specificity += 0.3
        elif features.entity_count > 2:
            specificity += 0.15
        if features.regulation_citations > 0:
            specificity += 0.3
        if features.days_until_effective is not None:
            specificity += 0.2
        if features.days_until_deadline is not None:
            specificity += 0.2
        features.specificity_score = min(1.0, specificity)

        return features


def extract_features_batch(signals: list[dict]) -> list[FeatureSet]:
    """Extract features for multiple signals."""
    extractor = FeatureExtractor()
    return [extractor.extract(signal) for signal in signals]
