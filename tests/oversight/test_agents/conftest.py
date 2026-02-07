"""Reset circuit breakers between oversight agent tests.

The oversight agents use module-level circuit breaker singletons.
Without resetting, a CB tripped open by one test stays open for the next.
"""

import pytest

from src.resilience.circuit_breaker import CircuitBreaker, CircuitMetrics, CircuitState


@pytest.fixture(autouse=True)
def reset_circuit_breakers():
    """Reset all circuit breakers to CLOSED before each test."""
    for cb in CircuitBreaker._registry.values():
        cb._state = CircuitState.CLOSED
        cb._metrics = CircuitMetrics()
        cb._opened_at = None
        cb._half_open_calls = 0
    yield
