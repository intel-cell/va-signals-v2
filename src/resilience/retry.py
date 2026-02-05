"""
Retry with Exponential Backoff.

Provides automatic retry for transient failures with configurable
backoff strategies.
"""

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from functools import wraps
from typing import Callable, TypeVar, ParamSpec, Optional, Union

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_attempts: int = 3
    base_delay: float = 1.0              # Initial delay in seconds
    max_delay: float = 60.0              # Maximum delay
    exponential_base: float = 2.0        # Exponential backoff multiplier
    jitter: bool = True                  # Add randomness to delay
    jitter_factor: float = 0.1           # Jitter as fraction of delay
    retry_exceptions: tuple = (Exception,)  # Exceptions to retry
    no_retry_exceptions: tuple = ()       # Exceptions to NOT retry


@dataclass
class RetryStats:
    """Statistics from a retry operation."""
    attempts: int = 0
    total_delay: float = 0.0
    success: bool = False
    final_exception: Optional[Exception] = None


def calculate_delay(
    attempt: int,
    config: RetryConfig
) -> float:
    """Calculate delay for a given attempt number."""
    # Exponential backoff
    delay = config.base_delay * (config.exponential_base ** (attempt - 1))

    # Cap at maximum
    delay = min(delay, config.max_delay)

    # Add jitter
    if config.jitter:
        jitter_range = delay * config.jitter_factor
        delay = delay + random.uniform(-jitter_range, jitter_range)

    return max(0, delay)


def should_retry(
    exc: Exception,
    config: RetryConfig
) -> bool:
    """Determine if an exception should trigger a retry."""
    # Never retry these
    if config.no_retry_exceptions and isinstance(exc, config.no_retry_exceptions):
        return False

    # Only retry these
    return isinstance(exc, config.retry_exceptions)


async def retry_with_backoff(
    func: Callable[P, T],
    *args: P.args,
    config: RetryConfig = None,
    on_retry: Callable[[int, Exception, float], None] = None,
    **kwargs: P.kwargs
) -> T:
    """
    Execute a function with retry and exponential backoff.

    Args:
        func: Function to call (sync or async)
        *args: Positional arguments for func
        config: Retry configuration
        on_retry: Callback called on each retry (attempt, exception, delay)
        **kwargs: Keyword arguments for func

    Returns:
        Result from successful function call

    Raises:
        Exception: If all retries exhausted, raises last exception

    Usage:
        result = await retry_with_backoff(
            fetch_data,
            url,
            config=RetryConfig(max_attempts=5),
            on_retry=lambda a, e, d: logger.warning(f"Retry {a}: {e}")
        )
    """
    config = config or RetryConfig()
    stats = RetryStats()
    last_exception: Optional[Exception] = None

    for attempt in range(1, config.max_attempts + 1):
        stats.attempts = attempt

        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            stats.success = True
            return result

        except Exception as e:
            last_exception = e
            stats.final_exception = e

            # Check if we should retry
            if not should_retry(e, config):
                logger.debug(f"Not retrying {func.__name__}: {type(e).__name__} not in retry list")
                raise

            # Check if we have more attempts
            if attempt >= config.max_attempts:
                logger.warning(
                    f"All {config.max_attempts} attempts failed for {func.__name__}: {e}"
                )
                raise

            # Calculate delay
            delay = calculate_delay(attempt, config)
            stats.total_delay += delay

            # Log and callback
            logger.info(
                f"Retry {attempt}/{config.max_attempts} for {func.__name__} "
                f"after {delay:.2f}s: {type(e).__name__}: {e}"
            )

            if on_retry:
                on_retry(attempt, e, delay)

            # Wait before retry
            await asyncio.sleep(delay)

    # Should not reach here, but just in case
    if last_exception:
        raise last_exception
    raise RuntimeError("Retry loop exited unexpectedly")


def retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    retry_exceptions: tuple = (Exception,),
    no_retry_exceptions: tuple = (),
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Decorator for retry with backoff.

    Usage:
        @retry(max_attempts=5, base_delay=2.0)
        async def fetch_data():
            ...
    """
    config = RetryConfig(
        max_attempts=max_attempts,
        base_delay=base_delay,
        max_delay=max_delay,
        retry_exceptions=retry_exceptions,
        no_retry_exceptions=no_retry_exceptions,
    )

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                return await retry_with_backoff(func, *args, config=config, **kwargs)
            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                return asyncio.get_event_loop().run_until_complete(
                    retry_with_backoff(func, *args, config=config, **kwargs)
                )
            return sync_wrapper

    return decorator


# Pre-configured retry decorators for common scenarios

def retry_api_call(func: Callable[P, T]) -> Callable[P, T]:
    """Retry decorator for external API calls."""
    return retry(
        max_attempts=3,
        base_delay=2.0,
        max_delay=30.0,
        retry_exceptions=(
            ConnectionError,
            TimeoutError,
            OSError,
        ),
    )(func)


def retry_database(func: Callable[P, T]) -> Callable[P, T]:
    """Retry decorator for database operations."""
    return retry(
        max_attempts=3,
        base_delay=0.5,
        max_delay=5.0,
    )(func)
