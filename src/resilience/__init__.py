"""
Resilience module for error handling and fault tolerance.

Provides:
- Circuit breaker pattern
- Automatic retry with exponential backoff
- Rate limiting
- Bulkhead isolation
- Sync-friendly wiring helpers for fetch modules
"""

from .circuit_breaker import CircuitBreaker, CircuitBreakerOpen, CircuitState
from .failure_correlator import (
    CorrelatedIncident,
    detect_circuit_breaker_cascade,
    detect_correlated_failures,
    get_current_incident,
    get_recent_incidents,
)
from .health_score import AggregateHealth, HealthDimension, compute_health_score
from .rate_limiter import RateLimiter, RateLimitExceeded
from .retry import RetryConfig, retry_with_backoff
from .staleness_monitor import (
    SourceExpectation,
    StaleSourceAlert,
    check_all_sources,
    check_source,
    load_expectations,
)
from .wiring import (
    GLOBAL_HTTP_TIMEOUT,
    FetchTimeout,
    circuit_breaker_sync,
    with_timeout,
)

__all__ = [
    "CircuitBreaker",
    "CircuitState",
    "CircuitBreakerOpen",
    "retry_with_backoff",
    "RetryConfig",
    "RateLimiter",
    "RateLimitExceeded",
    "StaleSourceAlert",
    "SourceExpectation",
    "check_all_sources",
    "check_source",
    "load_expectations",
    "circuit_breaker_sync",
    "with_timeout",
    "FetchTimeout",
    "GLOBAL_HTTP_TIMEOUT",
    "CorrelatedIncident",
    "detect_correlated_failures",
    "detect_circuit_breaker_cascade",
    "get_recent_incidents",
    "get_current_incident",
    "AggregateHealth",
    "HealthDimension",
    "compute_health_score",
]
