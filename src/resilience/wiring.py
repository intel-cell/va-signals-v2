"""
Sync-friendly resilience wiring for fetch modules.

Provides decorators and helpers to wrap synchronous HTTP calls
with circuit breaker protection and global timeout enforcement.
"""

import asyncio
import functools
import logging
import signal
from collections.abc import Callable
from datetime import UTC
from typing import ParamSpec, TypeVar

from .circuit_breaker import CircuitBreaker, CircuitBreakerOpen

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")

# Global timeout for all scraper/HTTP calls (seconds)
GLOBAL_HTTP_TIMEOUT = 45


class FetchTimeout(Exception):
    """Raised when a fetch call exceeds the global timeout."""

    def __init__(self, name: str, timeout: float):
        self.name = name
        self.timeout = timeout
        super().__init__(f"Fetch '{name}' timed out after {timeout}s")


def _run_coro_sync(coro):
    """Run an async coroutine synchronously, safe even if an event loop is already running."""
    try:
        asyncio.get_running_loop()
        # Event loop already running (e.g. Playwright) — use a thread with its own loop.
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        # No running loop — safe to use asyncio.run() directly.
        return asyncio.run(coro)


def circuit_breaker_sync(cb: CircuitBreaker):
    """
    Decorator that wraps a synchronous function with circuit breaker protection.

    Records success/failure with the given circuit breaker instance.
    Raises CircuitBreakerOpen if the circuit is open.

    Usage:
        from src.resilience.circuit_breaker import congress_api_cb

        @circuit_breaker_sync(congress_api_cb)
        def _fetch_json(url, api_key):
            ...
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            # Check if circuit is open
            try:
                _run_coro_sync(cb._check_state())
            except Exception:
                pass

            if cb.state.value == "open":
                cb._metrics.rejected_calls += 1
                from datetime import datetime

                until = datetime.now(UTC)
                raise CircuitBreakerOpen(cb.name, until)

            try:
                result = func(*args, **kwargs)
                # Record success
                try:
                    _run_coro_sync(cb._record_success())
                except Exception:
                    pass
                return result
            except CircuitBreakerOpen:
                raise
            except Exception as e:
                # Record failure if it should count
                if cb._should_count_failure(e):
                    try:
                        _run_coro_sync(cb._record_failure())
                    except Exception:
                        pass
                raise

        return wrapper

    return decorator


def with_timeout(timeout: float = GLOBAL_HTTP_TIMEOUT, name: str = "fetch"):
    """
    Decorator that enforces a timeout on a synchronous function.

    Uses signal-based timeout on Unix systems.
    Falls through (no timeout enforcement) on non-Unix or when
    not running in the main thread.

    Usage:
        @with_timeout(45, name="congress_api")
        def _fetch_json(url, api_key):
            ...
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            import threading

            # signal.alarm only works in main thread on Unix
            if threading.current_thread() is not threading.main_thread():
                return func(*args, **kwargs)

            def _timeout_handler(signum, frame):
                raise FetchTimeout(name, timeout)

            old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(int(timeout))
            try:
                return func(*args, **kwargs)
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)

        return wrapper

    return decorator
