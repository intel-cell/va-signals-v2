"""Classification for state intelligence signals."""

import re
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
    # Program disruptions (include common forms)
    "suspend",
    "suspends",
    "suspended",
    "suspension",
    "terminate",
    "terminates",
    "terminated",
    "termination",
    "cancel",
    "cancels",
    "canceled",
    "cancelled",
    "cancellation",
    "halt",
    "halts",
    "halted",
    "pause",
    "pauses",
    "paused",
    "defund",
    "defunds",
    "defunded",
    "defunding",
    "eliminate",
    "eliminates",
    "eliminated",
    "elimination",
    "discontinue",
    "discontinues",
    "discontinued",
    # Problems
    "backlog",
    "backlogs",
    "delay",
    "delays",
    "delayed",
    "shortage",
    "shortages",
    "crisis",
    "failure",
    "failures",
    "investigation",
    "investigations",
    "audit finding",
    "audit findings",
    "misconduct",
    # Cuts
    "budget cut",
    "budget cuts",
    "funding cut",
    "funding cuts",
    "layoff",
    "layoffs",
    "closure",
    "closures",
]

MEDIUM_SEVERITY_KEYWORDS = [
    # Leadership changes
    "resign",
    "resigns",
    "resigned",
    "resignation",
    "retire",
    "retires",
    "retired",
    "retirement",
    "appoint",
    "appoints",
    "appointed",
    "appointment",
    "nomination",
    "nominations",
    # Policy shifts
    "overhaul",
    "overhauls",
    "overhauled",
    "reform",
    "reforms",
    "reformed",
    "restructure",
    "restructures",
    "restructured",
    "restructuring",
    "review",
    "reviews",
    "reviewed",
    # Access issues
    "wait time",
    "wait times",
    "access issue",  # More specific to avoid false positives
    "access issues",
    "capacity issue",  # More specific
    "capacity issues",
]


# Pre-compile patterns with word boundaries
def _compile_keyword_patterns(keywords: list[str]) -> list[tuple[str, re.Pattern]]:
    """Compile keywords to regex patterns with word boundaries."""
    patterns = []
    for kw in keywords:
        # Use word boundaries for whole words/phrases
        pattern = re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)
        patterns.append((kw, pattern))
    return patterns


_HIGH_PATTERNS = _compile_keyword_patterns(HIGH_SEVERITY_KEYWORDS)
_MEDIUM_PATTERNS = _compile_keyword_patterns(MEDIUM_SEVERITY_KEYWORDS)


def classify_by_keywords(
    title: str, content: Optional[str] = None
) -> ClassificationResult:
    """
    Classify signal severity by keyword matching.

    Used for official sources where content is structured.
    Uses word boundaries to prevent false positives from substrings.
    """
    text = f"{title} {content or ''}"

    # Check high-severity keywords
    high_matches = [kw for kw, pattern in _HIGH_PATTERNS if pattern.search(text)]
    if high_matches:
        return ClassificationResult(
            severity="high",
            method="keyword",
            keywords_matched=high_matches,
        )

    # Check medium-severity keywords
    medium_matches = [kw for kw, pattern in _MEDIUM_PATTERNS if pattern.search(text)]
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
