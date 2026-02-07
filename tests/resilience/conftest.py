"""Isolate resilience tests from global registry contamination.

CircuitBreaker._registry and RateLimiter._registry are class-level dicts
that accumulate entries across the entire test session.  Without cleanup,
tests that pass in isolation fail in the full suite because:

1. Pre-configured singletons (10 CBs, 4 rate limiters) bleed state.
2. Test-created instances persist and collide on re-used names.
3. Metrics/state from earlier tests pollute later assertions.

Fix: snapshot the registries before each test, restore them after.
"""

import pytest

from src.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitMetrics,
    CircuitState,
)
from src.resilience.rate_limiter import RateLimiter, RateLimiterState


@pytest.fixture(autouse=True)
def isolate_circuit_breaker_registry():
    """Save and restore CircuitBreaker._registry around each test."""
    original = CircuitBreaker._registry.copy()

    # Reset all pre-existing CBs to clean state
    for cb in CircuitBreaker._registry.values():
        cb._state = CircuitState.CLOSED
        cb._metrics = CircuitMetrics()
        cb._opened_at = None
        cb._half_open_calls = 0

    yield

    # Remove any entries added during the test, restore originals
    CircuitBreaker._registry.clear()
    CircuitBreaker._registry.update(original)


@pytest.fixture(autouse=True)
def isolate_rate_limiter_registry():
    """Save and restore RateLimiter._registry around each test."""
    import time

    original = RateLimiter._registry.copy()

    # Reset all pre-existing limiters to full token bucket
    for rl in RateLimiter._registry.values():
        rl._state = RateLimiterState(
            tokens=float(rl.config.burst),
            last_update=time.time(),
        )

    yield

    RateLimiter._registry.clear()
    RateLimiter._registry.update(original)
