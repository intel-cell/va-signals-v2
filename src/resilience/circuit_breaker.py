"""
Circuit Breaker Pattern Implementation.

Prevents cascading failures by failing fast when a service is unhealthy.

States:
- CLOSED: Normal operation, requests pass through
- OPEN: Service failing, requests fail immediately
- HALF_OPEN: Testing if service recovered

Transitions:
- CLOSED → OPEN: When failure threshold is reached
- OPEN → HALF_OPEN: After recovery timeout
- HALF_OPEN → CLOSED: If test request succeeds
- HALF_OPEN → OPEN: If test request fails
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from functools import wraps
from typing import Callable, Optional, Any, TypeVar, ParamSpec

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpen(Exception):
    """Raised when circuit is open and request is rejected."""
    def __init__(self, name: str, until: datetime):
        self.name = name
        self.until = until
        super().__init__(f"Circuit '{name}' is open until {until.isoformat()}")


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    failure_threshold: int = 5          # Failures before opening
    success_threshold: int = 2          # Successes to close from half-open
    timeout_seconds: float = 60.0       # Time in open state before half-open
    half_open_max_calls: int = 3        # Max calls allowed in half-open
    exclude_exceptions: tuple = ()       # Exceptions that don't count as failures
    include_exceptions: tuple = (Exception,)  # Only these count as failures


@dataclass
class CircuitMetrics:
    """Metrics for a circuit breaker."""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    state_changes: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    last_state_change: Optional[float] = None
    consecutive_failures: int = 0
    consecutive_successes: int = 0


class CircuitBreaker:
    """
    Circuit breaker implementation.

    Usage:
        # Create circuit breaker
        cb = CircuitBreaker("external_api")

        # Use as decorator
        @cb
        async def call_external_api():
            ...

        # Or use call method
        result = await cb.call(call_external_api)

        # Check state
        if cb.state == CircuitState.OPEN:
            print("Service is down!")
    """

    # Global registry of circuit breakers
    _registry: dict[str, "CircuitBreaker"] = {}

    def __init__(
        self,
        name: str,
        config: CircuitBreakerConfig = None,
    ):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._metrics = CircuitMetrics()
        self._opened_at: Optional[float] = None
        self._half_open_calls = 0
        self._lock = asyncio.Lock()

        # Register this circuit breaker
        CircuitBreaker._registry[name] = self

        logger.info(f"Circuit breaker '{name}' initialized")

    @property
    def state(self) -> CircuitState:
        """Current circuit state."""
        return self._state

    @property
    def metrics(self) -> CircuitMetrics:
        """Circuit metrics."""
        return self._metrics

    @classmethod
    def get(cls, name: str) -> Optional["CircuitBreaker"]:
        """Get a circuit breaker by name."""
        return cls._registry.get(name)

    @classmethod
    def all(cls) -> dict[str, "CircuitBreaker"]:
        """Get all registered circuit breakers."""
        return cls._registry.copy()

    async def _check_state(self) -> None:
        """Check and potentially transition state."""
        now = time.time()

        if self._state == CircuitState.OPEN:
            # Check if timeout has passed
            if self._opened_at and (now - self._opened_at) >= self.config.timeout_seconds:
                await self._transition_to(CircuitState.HALF_OPEN)

    async def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state."""
        old_state = self._state
        self._state = new_state
        self._metrics.state_changes += 1
        self._metrics.last_state_change = time.time()

        if new_state == CircuitState.OPEN:
            self._opened_at = time.time()
            self._half_open_calls = 0

        if new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0

        if new_state == CircuitState.CLOSED:
            self._metrics.consecutive_failures = 0

        logger.info(f"Circuit '{self.name}' transitioned: {old_state.value} → {new_state.value}")

    async def _record_success(self) -> None:
        """Record a successful call."""
        self._metrics.total_calls += 1
        self._metrics.successful_calls += 1
        self._metrics.consecutive_successes += 1
        self._metrics.consecutive_failures = 0
        self._metrics.last_success_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            if self._metrics.consecutive_successes >= self.config.success_threshold:
                await self._transition_to(CircuitState.CLOSED)

    async def _record_failure(self) -> None:
        """Record a failed call."""
        self._metrics.total_calls += 1
        self._metrics.failed_calls += 1
        self._metrics.consecutive_failures += 1
        self._metrics.consecutive_successes = 0
        self._metrics.last_failure_time = time.time()

        if self._state == CircuitState.CLOSED:
            if self._metrics.consecutive_failures >= self.config.failure_threshold:
                await self._transition_to(CircuitState.OPEN)

        elif self._state == CircuitState.HALF_OPEN:
            await self._transition_to(CircuitState.OPEN)

    def _should_count_failure(self, exc: Exception) -> bool:
        """Check if exception should count as a failure."""
        # Excluded exceptions never count
        if self.config.exclude_exceptions and isinstance(exc, self.config.exclude_exceptions):
            return False

        # Must be an included exception
        return isinstance(exc, self.config.include_exceptions)

    async def call(self, func: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
        """
        Execute function through the circuit breaker.

        Args:
            func: Function to call (sync or async)
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Function result

        Raises:
            CircuitBreakerOpen: If circuit is open
            Exception: Any exception from the function
        """
        async with self._lock:
            await self._check_state()

            if self._state == CircuitState.OPEN:
                self._metrics.rejected_calls += 1
                until = datetime.fromtimestamp(
                    self._opened_at + self.config.timeout_seconds,
                    tz=timezone.utc
                )
                raise CircuitBreakerOpen(self.name, until)

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self.config.half_open_max_calls:
                    self._metrics.rejected_calls += 1
                    until = datetime.now(timezone.utc)
                    raise CircuitBreakerOpen(self.name, until)
                self._half_open_calls += 1

        try:
            # Call the function
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            async with self._lock:
                await self._record_success()

            return result

        except Exception as e:
            async with self._lock:
                if self._should_count_failure(e):
                    await self._record_failure()
            raise

    def __call__(self, func: Callable[P, T]) -> Callable[P, T]:
        """Use as decorator."""
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                return await self.call(func, *args, **kwargs)
            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                return asyncio.get_event_loop().run_until_complete(
                    self.call(func, *args, **kwargs)
                )
            return sync_wrapper

    def reset(self) -> None:
        """Manually reset the circuit breaker to closed state."""
        self._state = CircuitState.CLOSED
        self._metrics.consecutive_failures = 0
        self._metrics.consecutive_successes = 0
        self._opened_at = None
        self._half_open_calls = 0
        logger.info(f"Circuit '{self.name}' manually reset")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "name": self.name,
            "state": self._state.value,
            "metrics": {
                "total_calls": self._metrics.total_calls,
                "successful_calls": self._metrics.successful_calls,
                "failed_calls": self._metrics.failed_calls,
                "rejected_calls": self._metrics.rejected_calls,
                "state_changes": self._metrics.state_changes,
                "consecutive_failures": self._metrics.consecutive_failures,
                "consecutive_successes": self._metrics.consecutive_successes,
            },
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "success_threshold": self.config.success_threshold,
                "timeout_seconds": self.config.timeout_seconds,
            },
            "opened_at": datetime.fromtimestamp(
                self._opened_at, tz=timezone.utc
            ).isoformat() if self._opened_at else None,
        }


# Pre-configured circuit breakers for common services
federal_register_cb = CircuitBreaker(
    "federal_register",
    CircuitBreakerConfig(
        failure_threshold=3,
        timeout_seconds=300,  # 5 minutes
    )
)

congress_api_cb = CircuitBreaker(
    "congress_api",
    CircuitBreakerConfig(
        failure_threshold=3,
        timeout_seconds=300,
    )
)

database_cb = CircuitBreaker(
    "database",
    CircuitBreakerConfig(
        failure_threshold=5,
        timeout_seconds=30,
    )
)
