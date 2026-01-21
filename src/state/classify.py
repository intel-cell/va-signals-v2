"""Classification for state intelligence signals."""

import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from typing import Optional

HAIKU_MODEL = "claude-3-haiku-20240307"


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


logger = logging.getLogger(__name__)

HAIKU_PROMPT = """Analyze this news article about veterans in {state}.

Title: {title}
Content: {content}

Questions:
1. Does this report a SPECIFIC, DATED event (not a general explainer)?
2. Does it indicate a problem with federal program implementation (PACT Act, Community Care, VHA)?
3. Severity: Is this a disruption/failure (HIGH), policy shift (MEDIUM), or routine/positive news (LOW)?

Respond as JSON only:
{{"is_specific_event": bool, "federal_program": str|null, "severity": "high"|"medium"|"low"|"noise", "reasoning": str}}"""


def _get_api_key() -> str:
    """Get Anthropic API key from Keychain."""
    result = subprocess.run(
        ["security", "find-generic-password", "-s", "claude-api", "-w"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError("Could not retrieve claude-api key from Keychain")
    return result.stdout.strip()


def _call_haiku(prompt: str) -> dict:
    """Call Haiku model and return parsed JSON response."""
    import anthropic

    client = anthropic.Anthropic(api_key=_get_api_key())

    response = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )

    # Extract text and parse JSON
    text = response.content[0].text

    # Find JSON in response
    start = text.find("{")
    end = text.rfind("}") + 1
    if start < 0 or end <= start:
        raise ValueError(f"No JSON object found in response: {text[:200]}")

    try:
        result = json.loads(text[start:end])
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in response: {e}")

    # Validate required fields
    if "severity" not in result:
        raise ValueError(f"Missing 'severity' field in response: {result}")
    if result["severity"] not in ("high", "medium", "low", "noise"):
        raise ValueError(f"Invalid severity value: {result['severity']}")

    return result


def classify_by_llm(
    title: str,
    content: Optional[str],
    state: str,
) -> ClassificationResult:
    """
    Classify signal using LLM (Haiku).

    Used for news sources where content is unstructured.
    Falls back to keyword classification on error.
    """
    try:
        prompt = HAIKU_PROMPT.format(
            state=state,
            title=title,
            content=content or "(no content)",
        )

        result = _call_haiku(prompt)

        # Filter out noise (non-events, explainers)
        if not result.get("is_specific_event") or result.get("severity") == "noise":
            return ClassificationResult(
                severity="noise",
                method="llm",
                llm_reasoning=result.get("reasoning"),
            )

        return ClassificationResult(
            severity=result["severity"],
            method="llm",
            llm_reasoning=result.get("reasoning"),
        )

    except Exception as e:
        logger.warning(f"LLM classification failed, falling back to keywords: {e}")
        return classify_by_keywords(title, content)
