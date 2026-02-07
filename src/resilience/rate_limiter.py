"""
Rate Limiter Implementation.

Provides rate limiting using token bucket algorithm.
"""

import asyncio
import logging
import threading
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded."""

    def __init__(self, name: str, retry_after: float):
        self.name = name
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded for '{name}'. Retry after {retry_after:.1f}s")


@dataclass
class RateLimiterConfig:
    """Configuration for rate limiter."""

    rate: float  # Tokens per second
    burst: int  # Maximum bucket capacity
    name: str = "default"


@dataclass
class RateLimiterState:
    """State for a rate limiter."""

    tokens: float
    last_update: float
    total_allowed: int = 0
    total_denied: int = 0


class RateLimiter:
    """
    Token bucket rate limiter.

    Allows bursts up to 'burst' size, then limits to 'rate' requests per second.

    Usage:
        limiter = RateLimiter(rate=10, burst=20, name="api")

        if limiter.allow():
            # Proceed with request
            ...
        else:
            # Rate limited
            raise RateLimitExceeded(limiter.name, limiter.retry_after())

        # Or use async context manager
        async with limiter.acquire():
            # Proceed with request
            ...
    """

    # Global registry
    _registry: dict[str, "RateLimiter"] = {}
    _registry_lock = threading.Lock()

    def __init__(self, rate: float, burst: int, name: str = "default"):
        self.config = RateLimiterConfig(rate=rate, burst=burst, name=name)
        self._state = RateLimiterState(tokens=float(burst), last_update=time.time())
        self._lock = asyncio.Lock()

        with RateLimiter._registry_lock:
            RateLimiter._registry[name] = self

    @classmethod
    def get(cls, name: str) -> Optional["RateLimiter"]:
        """Get a rate limiter by name."""
        with cls._registry_lock:
            return cls._registry.get(name)

    @classmethod
    def all(cls) -> dict[str, "RateLimiter"]:
        """Get all registered rate limiters."""
        with cls._registry_lock:
            return cls._registry.copy()

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self._state.last_update
        self._state.tokens = min(self.config.burst, self._state.tokens + elapsed * self.config.rate)
        self._state.last_update = now

    def allow(self, tokens: float = 1.0) -> bool:
        """
        Check if request is allowed and consume tokens.

        Args:
            tokens: Number of tokens to consume (default 1)

        Returns:
            True if allowed, False if rate limited
        """
        self._refill()

        if self._state.tokens >= tokens:
            self._state.tokens -= tokens
            self._state.total_allowed += 1
            return True
        else:
            self._state.total_denied += 1
            return False

    async def allow_async(self, tokens: float = 1.0) -> bool:
        """Async version of allow()."""
        async with self._lock:
            return self.allow(tokens)

    def retry_after(self) -> float:
        """Calculate seconds until next token is available."""
        if self._state.tokens >= 1:
            return 0.0
        tokens_needed = 1 - self._state.tokens
        return tokens_needed / self.config.rate

    async def acquire(self, tokens: float = 1.0, timeout: float = None):
        """
        Async context manager that waits for tokens.

        Args:
            tokens: Number of tokens to acquire
            timeout: Maximum seconds to wait (None = wait forever)

        Raises:
            RateLimitExceeded: If timeout exceeded
        """
        return _RateLimitAcquireContext(self, tokens, timeout)

    @property
    def available_tokens(self) -> float:
        """Current available tokens."""
        self._refill()
        return self._state.tokens

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        self._refill()
        return {
            "name": self.config.name,
            "rate": self.config.rate,
            "burst": self.config.burst,
            "available_tokens": round(self._state.tokens, 2),
            "total_allowed": self._state.total_allowed,
            "total_denied": self._state.total_denied,
        }


class _RateLimitAcquireContext:
    """Async context manager for rate limit acquisition."""

    def __init__(self, limiter: RateLimiter, tokens: float, timeout: float):
        self.limiter = limiter
        self.tokens = tokens
        self.timeout = timeout
        self._start_time = None

    async def __aenter__(self):
        self._start_time = time.time()

        while True:
            if await self.limiter.allow_async(self.tokens):
                return self

            # Check timeout
            if self.timeout is not None:
                elapsed = time.time() - self._start_time
                if elapsed >= self.timeout:
                    raise RateLimitExceeded(self.limiter.config.name, self.limiter.retry_after())

            # Wait a bit before trying again
            wait_time = min(
                self.limiter.retry_after(),
                0.1,  # Check at least every 100ms
            )
            await asyncio.sleep(wait_time)

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


# Pre-configured rate limiters for common scenarios

api_rate_limiter = RateLimiter(
    rate=100,  # 100 requests per second
    burst=200,  # Allow bursts up to 200
    name="api",
)

external_api_limiter = RateLimiter(
    rate=10,  # 10 requests per second to external APIs
    burst=20,
    name="external",
)

federal_register_limiter = RateLimiter(
    rate=5,  # Federal Register API rate limit
    burst=10,
    name="federal_register",
)

congress_api_limiter = RateLimiter(
    rate=10,  # Congress.gov API rate limit
    burst=20,
    name="congress",
)
