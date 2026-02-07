"""Haiku pre-filter classifier for oversight events."""

import json
import logging
from dataclasses import dataclass

import anthropic

from src.llm_config import HAIKU_MODEL
from src.resilience.circuit_breaker import CircuitBreakerOpen, anthropic_cb
from src.resilience.wiring import circuit_breaker_sync
from src.secrets import get_env_or_keychain

_llm_logger = logging.getLogger(__name__)


@dataclass
class ClassificationResult:
    """Result of event classification."""

    is_va_relevant: bool
    is_dated_action: bool
    rejection_reason: str | None = None
    routine_explanation: str | None = None

    @property
    def should_process(self) -> bool:
        """Event should be processed if VA-relevant and a dated action."""
        return self.is_va_relevant and self.is_dated_action


def _get_client() -> anthropic.Anthropic:
    """Get Anthropic client with API key from environment."""
    api_key = get_env_or_keychain("ANTHROPIC_API_KEY", "claude-api")
    return anthropic.Anthropic(api_key=api_key)


@circuit_breaker_sync(anthropic_cb)
def _call_haiku(prompt: str, system: str) -> str:
    """Call Haiku model and return response text."""
    client = _get_client()
    response = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=256,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


VA_RELEVANCE_SYSTEM = """You are a classifier that determines if a document is relevant to the U.S. Department of Veterans Affairs (VA).

VA-relevant content includes:
- VA healthcare, benefits, claims, appeals
- Veterans' issues, programs, or policies
- GAO/OIG reports about VA
- Congressional oversight of VA
- VA budget, personnel, or operations
- CAFC/BVA veterans' cases

NOT VA-relevant:
- Other government agencies (DOD, HHS, etc.) unless directly about VA
- General government news without VA connection
- State-level veterans affairs (unless federal VA involved)

Respond with ONLY valid JSON: {"is_va_relevant": true/false, "explanation": "brief reason"}"""


DATED_ACTION_SYSTEM = """You are a classifier that determines if a document describes a CURRENT, DATED ACTION versus a historical reference or evergreen content.

DATED ACTION (current, newsworthy):
- New report released, investigation launched
- Hearing announced or held
- Legislation introduced or passed
- New policy announced
- Recent event being reported

NOT DATED ACTION (historical or evergreen):
- Reference to past events (e.g., "the 2019 investigation...")
- Explainer or background content
- How-to guides or resource pages
- General information without a specific recent event

Respond with ONLY valid JSON: {"is_dated_action": true/false, "explanation": "brief reason"}"""


def is_va_relevant(title: str, content: str) -> dict:
    """
    Check if content is VA-relevant using Haiku.

    Args:
        title: Event title
        content: Event content/excerpt

    Returns:
        Dict with is_va_relevant (bool) and explanation (str)
    """
    prompt = f"Title: {title}\n\nContent: {content[:1000]}"

    try:
        response_text = _call_haiku(prompt, VA_RELEVANCE_SYSTEM)
        return json.loads(response_text)
    except CircuitBreakerOpen as exc:
        _llm_logger.warning("Anthropic circuit breaker OPEN in classifier: %s", exc)
        return {
            "is_va_relevant": True,
            "explanation": f"Circuit breaker open: {exc} - assuming relevant",
        }
    except (json.JSONDecodeError, KeyError, RuntimeError) as exc:
        # Fail open - assume relevant if we can't classify
        return {
            "is_va_relevant": True,
            "explanation": f"Classification error: {exc} - assuming relevant",
        }


def is_dated_action(title: str, content: str) -> dict:
    """
    Check if content describes a dated action using Haiku.

    Args:
        title: Event title
        content: Event content/excerpt

    Returns:
        Dict with is_dated_action (bool) and explanation (str)
    """
    prompt = f"Title: {title}\n\nContent: {content[:1000]}"

    try:
        response_text = _call_haiku(prompt, DATED_ACTION_SYSTEM)
        return json.loads(response_text)
    except CircuitBreakerOpen as exc:
        _llm_logger.warning("Anthropic circuit breaker OPEN in classifier: %s", exc)
        return {
            "is_dated_action": True,
            "explanation": f"Circuit breaker open: {exc} - assuming dated",
        }
    except (json.JSONDecodeError, KeyError, RuntimeError) as exc:
        # Fail open - assume dated action if we can't classify
        return {
            "is_dated_action": True,
            "explanation": f"Classification error: {exc} - assuming dated",
        }


def classify_event(title: str, content: str) -> ClassificationResult:
    """
    Full classification of an event.

    Args:
        title: Event title
        content: Event content/excerpt

    Returns:
        ClassificationResult with all checks
    """
    # Check VA relevance first
    va_result = is_va_relevant(title, content)
    if not va_result.get("is_va_relevant", True):
        return ClassificationResult(
            is_va_relevant=False,
            is_dated_action=False,  # Not checked
            rejection_reason="not_va_relevant",
            routine_explanation=va_result.get("explanation"),
        )

    # Check if dated action
    dated_result = is_dated_action(title, content)
    if not dated_result.get("is_dated_action", True):
        return ClassificationResult(
            is_va_relevant=True,
            is_dated_action=False,
            rejection_reason="not_dated_action",
            routine_explanation=dated_result.get("explanation"),
        )

    return ClassificationResult(
        is_va_relevant=True,
        is_dated_action=True,
    )
