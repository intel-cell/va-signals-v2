"""
Resilience module for error handling and fault tolerance.

Provides:
- Circuit breaker pattern
- Automatic retry with exponential backoff
- Rate limiting
- Bulkhead isolation
"""

from .circuit_breaker import CircuitBreaker, CircuitState, CircuitBreakerOpen
from .retry import retry_with_backoff, RetryConfig
from .rate_limiter import RateLimiter, RateLimitExceeded
from .staleness_monitor import (
    StaleSourceAlert,
    SourceExpectation,
    check_all_sources,
    check_source,
    load_expectations,
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
]
