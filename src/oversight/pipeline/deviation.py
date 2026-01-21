"""Sonnet deviation classifier for oversight events."""

import json
import os
from dataclasses import dataclass
from typing import Optional

import anthropic

from .baseline import BaselineSummary


SONNET_MODEL = "claude-sonnet-4-20250514"


@dataclass
class DeviationResult:
    """Result of deviation classification."""

    is_deviation: bool
    deviation_type: Optional[str]  # new_topic, frequency_spike, tone_shift, escalation, unprecedented
    confidence: float
    explanation: str


def _get_client() -> anthropic.Anthropic:
    """Get Anthropic client with API key from environment."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable not set")
    return anthropic.Anthropic(api_key=api_key)


DEVIATION_SYSTEM = """You are an expert analyst detecting deviations from baseline patterns in government oversight activity.

Given:
1. A new event (title + content)
2. A baseline summary of typical activity for this source

Determine if the new event represents a DEVIATION from the baseline pattern.

Deviation types:
- new_topic: Event covers a topic not seen in the baseline period
- frequency_spike: Unusual increase in activity on a topic
- tone_shift: Notably different tone (e.g., more critical, urgent)
- escalation: Event represents an escalation of previous activity
- unprecedented: First-of-its-kind action

NOT deviations:
- Routine periodic reports (quarterly, annual)
- Continuation of existing investigations
- Standard administrative actions
- Updates on known issues

Be conservative - only flag true deviations that would be newsworthy.

Respond with ONLY valid JSON:
{"is_deviation": true/false, "deviation_type": "type or null", "confidence": 0.0-1.0, "explanation": "brief reason"}"""


def check_deviation(
    title: str,
    content: str,
    baseline: BaselineSummary,
) -> DeviationResult:
    """
    Check if an event deviates from baseline patterns.

    Args:
        title: Event title
        content: Event content/excerpt
        baseline: Baseline summary to compare against

    Returns:
        DeviationResult with classification
    """
    # Build context from baseline
    baseline_context = f"""
Baseline for {baseline.source_type} ({baseline.window_start} to {baseline.window_end}):
- {baseline.event_count} events in baseline period
- Summary: {baseline.summary}
- Top topics: {', '.join(f'{k} ({v:.0%})' for k, v in baseline.topic_distribution.items())}
"""

    prompt = f"""
{baseline_context}

New event to evaluate:
Title: {title}

Content: {content[:1500]}

Is this event a deviation from the baseline pattern?
"""

    try:
        client = _get_client()
        response = client.messages.create(
            model=SONNET_MODEL,
            max_tokens=256,
            system=DEVIATION_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )

        result = json.loads(response.content[0].text)
        return DeviationResult(
            is_deviation=result.get("is_deviation", False),
            deviation_type=result.get("deviation_type"),
            confidence=result.get("confidence", 0.5),
            explanation=result.get("explanation", ""),
        )

    except (json.JSONDecodeError, KeyError, anthropic.APIError) as e:
        # Fail closed - don't flag as deviation if we can't classify
        return DeviationResult(
            is_deviation=False,
            deviation_type=None,
            confidence=0.0,
            explanation=f"Classification error: {str(e)}",
        )


def classify_deviation_type(
    event_topics: dict,
    baseline_topics: dict,
    threshold: float = 0.3,
) -> Optional[str]:
    """
    Quick heuristic classification of deviation type based on topic overlap.

    Args:
        event_topics: Topic distribution of the event
        baseline_topics: Topic distribution of the baseline
        threshold: Minimum overlap to consider similar

    Returns:
        Deviation type or None if not a deviation
    """
    if not event_topics or not baseline_topics:
        return None

    # Calculate topic overlap
    event_set = set(event_topics.keys())
    baseline_set = set(baseline_topics.keys())

    overlap = event_set & baseline_set
    new_topics = event_set - baseline_set

    # If most topics are new, it's a new topic deviation
    if len(new_topics) > len(overlap):
        return "new_topic"

    # Calculate weighted overlap
    overlap_score = sum(
        min(event_topics.get(t, 0), baseline_topics.get(t, 0))
        for t in overlap
    )

    if overlap_score < threshold:
        return "new_topic"

    return None


def check_deviation_simple(
    title: str,
    content: str,
    baseline: BaselineSummary,
) -> DeviationResult:
    """
    Simple heuristic deviation check (no LLM call).

    Use this for high-volume filtering before Sonnet classification.

    Args:
        title: Event title
        content: Event content/excerpt
        baseline: Baseline summary

    Returns:
        DeviationResult with heuristic classification
    """
    from .baseline import compute_topic_distribution

    # Get topic distribution of this event
    event_topics = compute_topic_distribution([{"title": title, "summary": content}])

    # Check for deviation
    deviation_type = classify_deviation_type(event_topics, baseline.topic_distribution)

    if deviation_type:
        return DeviationResult(
            is_deviation=True,
            deviation_type=deviation_type,
            confidence=0.6,  # Lower confidence for heuristic
            explanation=f"Heuristic: {deviation_type} detected",
        )

    return DeviationResult(
        is_deviation=False,
        deviation_type=None,
        confidence=0.6,
        explanation="Heuristic: matches baseline pattern",
    )
