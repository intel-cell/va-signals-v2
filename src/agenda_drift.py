"""
Agenda Drift Detection

Embedding-based detection of framing shifts in committee member utterances.
Compares new utterances against a member's historical baseline centroid.
"""

import math
from datetime import datetime, timezone

from .db import (
    get_ad_embeddings_for_member,
    insert_ad_baseline,
    get_latest_ad_baseline,
    insert_ad_deviation_event,
    get_ad_recent_deviations_for_hearing,
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
