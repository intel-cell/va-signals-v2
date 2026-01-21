"""
Agenda Drift Detection

Embedding-based detection of framing shifts in committee member utterances.
Compares new utterances against a member's historical baseline centroid.
"""

import math
import os
import subprocess
import time
from datetime import datetime, timezone
from typing import Optional

import requests

from .db import (
    get_ad_embeddings_for_member,
    insert_ad_baseline,
    get_latest_ad_baseline,
    insert_ad_deviation_event,
    get_ad_recent_deviations_for_hearing,
    get_ad_utterance_by_id,
    get_ad_typical_utterances,
)

# Thresholds (tunable)
DEVIATION_THRESHOLD_DIST = 0.20  # Minimum cosine distance to flag
DEVIATION_THRESHOLD_Z = 2.0      # Minimum z-score to flag
DEBOUNCE_K = 3                   # K of M utterances must exceed threshold
DEBOUNCE_M = 8                   # Window size for debounce


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def cosine_distance(a: list[float], b: list[float]) -> float:
    """
    Compute cosine distance: 1 - cosine_similarity.
    Returns 0.0 for identical vectors, 2.0 for opposite vectors.
    """
    if len(a) != len(b):
        raise ValueError(f"Vector dimension mismatch: {len(a)} vs {len(b)}")

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))

    if norm_a < 1e-9 or norm_b < 1e-9:
        return 1.0  # Degenerate case

    similarity = dot / (norm_a * norm_b)
    return 1.0 - similarity


def _mean_vector(vectors: list[list[float]]) -> list[float]:
    """Compute element-wise mean of vectors."""
    if not vectors:
        raise ValueError("Cannot compute mean of empty vector list")

    dim = len(vectors[0])
    n = len(vectors)
    return [sum(v[i] for v in vectors) / n for i in range(dim)]


def _std_dev(values: list[float], mean: float) -> float:
    """Compute sample standard deviation."""
    if len(values) < 2:
        return 0.0
    variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(variance)


def build_baseline(member_id: str) -> dict | None:
    """
    Build baseline from member's historical embeddings.

    Computes:
    - Centroid (mean vector) of all embeddings
    - mu/sigma of cosine distances from each embedding to centroid

    Returns dict with {member_id, vec_mean, mu, sigma, n, baseline_id}
    or None if insufficient data.
    """
    embeddings = get_ad_embeddings_for_member(member_id)

    if len(embeddings) < 5:
        return None  # Need minimum data for meaningful baseline

    vectors = [e[1] for e in embeddings]
    centroid = _mean_vector(vectors)

    # Compute distances from each embedding to centroid
    distances = [cosine_distance(v, centroid) for v in vectors]
    mu = sum(distances) / len(distances)
    sigma = _std_dev(distances, mu)

    # Persist baseline
    baseline_id = insert_ad_baseline(member_id, centroid, mu, sigma, len(vectors))

    return {
        "member_id": member_id,
        "vec_mean": centroid,
        "mu": mu,
        "sigma": sigma,
        "n": len(vectors),
        "baseline_id": baseline_id,
    }


def detect_deviation(
    member_id: str,
    utterance_id: str,
    vec: list[float],
    hearing_id: str,
    note: str = None,
) -> dict | None:
    """
    Compare utterance embedding to member's baseline.

    Returns deviation_event dict if flagged (dist >= threshold AND z >= threshold),
    else None.
    """
    baseline = get_latest_ad_baseline(member_id)
    if not baseline:
        return None  # No baseline yet

    centroid = baseline["vec_mean"]
    mu = baseline["mu"]
    sigma = baseline["sigma"]

    dist = cosine_distance(vec, centroid)

    # Compute z-score (handle zero sigma)
    if sigma < 1e-9:
        zscore = 0.0 if dist <= mu else 10.0  # Arbitrary high z if no variance
    else:
        zscore = (dist - mu) / sigma

    # Check thresholds
    if dist < DEVIATION_THRESHOLD_DIST or zscore < DEVIATION_THRESHOLD_Z:
        return None

    event = {
        "member_id": member_id,
        "hearing_id": hearing_id,
        "utterance_id": utterance_id,
        "baseline_id": baseline["id"],
        "cos_dist": round(dist, 4),
        "zscore": round(zscore, 2),
        "detected_at": _utc_now_iso(),
        "note": note,
    }

    event_id = insert_ad_deviation_event(event)
    event["id"] = event_id

    return event


def check_debounce(member_id: str, hearing_id: str) -> bool:
    """
    K-of-M debounce check.

    Returns True if at least K of the last M deviations for this member/hearing
    exceeded the z-score threshold (indicating sustained shift, not noise).
    """
    recent = get_ad_recent_deviations_for_hearing(member_id, hearing_id, limit=DEBOUNCE_M)

    if len(recent) < DEBOUNCE_K:
        return False  # Not enough data yet

    count_exceeding = sum(1 for d in recent if d["zscore"] >= DEVIATION_THRESHOLD_Z)
    return count_exceeding >= DEBOUNCE_K


def detect_with_debounce(
    member_id: str,
    utterance_id: str,
    vec: list[float],
    hearing_id: str,
    note: str = None,
) -> dict | None:
    """
    Detect deviation with K-of-M debounce applied.

    Only returns event if:
    1. Single utterance exceeds thresholds, AND
    2. K of last M utterances also exceeded threshold (sustained shift)

    Use this for production alerting to reduce false positives.
    """
    event = detect_deviation(member_id, utterance_id, vec, hearing_id, note)

    if not event:
        return None

    if not check_debounce(member_id, hearing_id):
        # Event recorded but not surfaced (debounce not met)
        event["debounce_passed"] = False
        return None

    event["debounce_passed"] = True
    return event


# -----------------------------------------------------------------------------
# LLM-powered deviation explanation
# -----------------------------------------------------------------------------

# Claude API config (matches src/summarize.py)
CLAUDE_MODEL = "claude-sonnet-4-20250514"
CLAUDE_MAX_TOKENS = 256
CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"

DEVIATION_SYSTEM_PROMPT = """You are an expert analyst specializing in Congressional hearing transcripts and political rhetoric.

Your task is to briefly explain why a committee member's statement differs from their typical focus areas.

Guidelines:
1. Be concise - respond in 1-2 sentences only
2. Focus on the topic/framing shift, not the quality of the statement
3. Use plain language accessible to a general audience
4. Be factual and neutral - do not editorialize

Example output: "This statement focuses on budget cuts, while they typically discuss veteran healthcare access."
"""


def _get_anthropic_key() -> Optional[str]:
    """Get Anthropic API key from environment or macOS Keychain."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    # Try macOS Keychain
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", "claude-api", "-a", os.environ.get("USER", ""), "-w"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _call_claude_for_explanation(
    system_prompt: str,
    user_prompt: str,
    api_key: str,
    timeout: int = 30,
) -> Optional[str]:
    """
    Make a message request to Claude API for deviation explanation.

    Args:
        system_prompt: System message content
        user_prompt: User message content
        api_key: Anthropic API key
        timeout: Request timeout in seconds

    Returns:
        Text response or None on error
    """
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    payload = {
        "model": CLAUDE_MODEL,
        "max_tokens": CLAUDE_MAX_TOKENS,
        "system": system_prompt,
        "messages": [
            {"role": "user", "content": user_prompt},
        ],
    }

    try:
        r = requests.post(CLAUDE_API_URL, headers=headers, json=payload, timeout=timeout)
        r.raise_for_status()

        data = r.json()
        content = data.get("content", [{}])[0].get("text", "")
        return content.strip() if content else None

    except requests.exceptions.RequestException as e:
        print(f"Claude API request error: {e}")
        return None
    except Exception as e:
        print(f"Claude API error: {e}")
        return None


def explain_deviation(member_id: str, flagged_utterance_id: str) -> Optional[str]:
    """
    Generate an LLM explanation for why an utterance deviates from a member's baseline.

    Args:
        member_id: The committee member ID
        flagged_utterance_id: The utterance ID that was flagged as a deviation

    Returns:
        A 1-2 sentence explanation string, or None if unable to generate
    """
    api_key = _get_anthropic_key()
    if not api_key:
        return None

    # Fetch the flagged utterance
    flagged = get_ad_utterance_by_id(flagged_utterance_id)
    if not flagged:
        return None

    # Fetch 3-5 typical utterances for comparison
    typical = get_ad_typical_utterances(
        member_id,
        exclude_utterance_id=flagged_utterance_id,
        limit=5,
    )

    if len(typical) < 3:
        # Not enough typical utterances for meaningful comparison
        return None

    # Build the user prompt
    member_name = flagged.get("member_name", member_id)

    typical_texts = "\n\n".join(
        f"Typical statement {i+1}: \"{u['content'][:500]}...\""
        if len(u["content"]) > 500 else f"Typical statement {i+1}: \"{u['content']}\""
        for i, u in enumerate(typical[:5])
    )

    flagged_text = flagged["content"]
    if len(flagged_text) > 500:
        flagged_text = flagged_text[:500] + "..."

    user_prompt = f"""Committee member: {member_name}

Here are some of their typical statements:

{typical_texts}

Here is the statement that was flagged as unusual:

Flagged statement: "{flagged_text}"

In 1-2 sentences, explain what topic or framing shift makes the flagged statement different from their typical focus areas."""

    explanation = _call_claude_for_explanation(
        DEVIATION_SYSTEM_PROMPT,
        user_prompt,
        api_key,
    )

    return explanation
