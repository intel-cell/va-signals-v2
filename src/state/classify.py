"""Classification for state intelligence signals."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ClassificationResult:
    """Result of signal classification."""

    severity: str  # "high", "medium", "low", "noise"
    method: str  # "keyword", "llm"
    keywords_matched: list[str] = field(default_factory=list)
    llm_reasoning: Optional[str] = None


HIGH_SEVERITY_KEYWORDS = [
    # Program disruptions
    "suspend",
    "terminate",
    "cancel",
    "halt",
    "pause",
    "defund",
    "eliminate",
    "discontinue",
    # Problems
    "backlog",
    "delay",
    "shortage",
    "crisis",
    "failure",
    "investigation",
    "audit finding",
    "misconduct",
    # Cuts
    "budget cut",
    "funding cut",
    "layoff",
    "closure",
]

MEDIUM_SEVERITY_KEYWORDS = [
    # Leadership changes
    "resign",
    "retire",
    "appoint",
    "nomination",
    # Policy shifts
    "overhaul",
    "reform",
    "restructure",
    "review",
    # Access issues
    "wait time",
    "access",
    "capacity",
]


def classify_by_keywords(
    title: str, content: Optional[str] = None
) -> ClassificationResult:
    """
    Classify signal severity by keyword matching.

    Used for official sources where content is structured.
    """
    text = f"{title} {content or ''}".lower()

    # Check high-severity keywords
    high_matches = [kw for kw in HIGH_SEVERITY_KEYWORDS if kw in text]
    if high_matches:
        return ClassificationResult(
            severity="high",
            method="keyword",
            keywords_matched=high_matches,
        )

    # Check medium-severity keywords
    medium_matches = [kw for kw in MEDIUM_SEVERITY_KEYWORDS if kw in text]
    if medium_matches:
        return ClassificationResult(
            severity="medium",
            method="keyword",
            keywords_matched=medium_matches,
        )

    # Default to low
    return ClassificationResult(
        severity="low",
        method="keyword",
        keywords_matched=[],
    )
