"""Tests for retry with exponential backoff."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.resilience.retry import (
    RetryConfig,
    RetryStats,
    calculate_delay,
    retry,
    retry_api_call,
    retry_database,
    retry_with_backoff,
    should_retry,
)


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# RetryConfig defaults
# ---------------------------------------------------------------------------

class TestRetryConfig:
    def test_defaults(self):
        cfg = RetryConfig()
        assert cfg.max_attempts == 3
        assert cfg.base_delay == 1.0
        assert cfg.max_delay == 60.0
        assert cfg.exponential_base == 2.0
        assert cfg.jitter is True
        assert cfg.jitter_factor == 0.1
        assert cfg.retry_exceptions == (Exception,)
        assert cfg.no_retry_exceptions == ()


# ---------------------------------------------------------------------------
# RetryStats defaults
# ---------------------------------------------------------------------------

class TestRetryStats:
    def test_defaults(self):
        s = RetryStats()
        assert s.attempts == 0
        assert s.total_delay == 0.0
        assert s.success is False
        assert s.final_exception is None


# ---------------------------------------------------------------------------
# calculate_delay
# ---------------------------------------------------------------------------

class TestCalculateDelay:
    def test_first_attempt(self):
        cfg = RetryConfig(base_delay=1.0, exponential_base=2.0, jitter=False)
        assert calculate_delay(1, cfg) == 1.0

    def test_second_attempt(self):
        cfg = RetryConfig(base_delay=1.0, exponential_base=2.0, jitter=False)
        assert calculate_delay(2, cfg) == 2.0

    def test_third_attempt(self):
        cfg = RetryConfig(base_delay=1.0, exponential_base=2.0, jitter=False)
        assert calculate_delay(3, cfg) == 4.0

    def test_max_delay_cap(self):
        cfg = RetryConfig(base_delay=10.0, exponential_base=10.0, max_delay=50.0, jitter=False)
        assert calculate_delay(3, cfg) == 50.0

    def test_jitter_stays_near_base(self):
        cfg = RetryConfig(base_delay=10.0, jitter=True, jitter_factor=0.1)
        delay = calculate_delay(1, cfg)
        assert 9.0 <= delay <= 11.0

    def test_delay_never_negative(self):
        cfg = RetryConfig(base_delay=0.001, jitter=True, jitter_factor=1.0)
        for attempt in range(1, 20):
            assert calculate_delay(attempt, cfg) >= 0


# ---------------------------------------------------------------------------
# should_retry
# ---------------------------------------------------------------------------

class TestShouldRetry:
    def test_retries_matching_exception(self):
        cfg = RetryConfig(retry_exceptions=(ConnectionError,))
        assert should_retry(ConnectionError(), cfg) is True

    def test_does_not_retry_non_matching(self):
        cfg = RetryConfig(retry_exceptions=(ConnectionError,))
        assert should_retry(ValueError(), cfg) is False

    def test_no_retry_exceptions_override(self):
        cfg = RetryConfig(
            retry_exceptions=(Exception,),
            no_retry_exceptions=(KeyboardInterrupt, ValueError),
        )
        assert should_retry(ValueError(), cfg) is False

    def test_retries_subclass(self):
        cfg = RetryConfig(retry_exceptions=(Exception,))
        assert should_retry(ConnectionError(), cfg) is True

    def test_empty_no_retry_tuple(self):
        cfg = RetryConfig(retry_exceptions=(Exception,), no_retry_exceptions=())
        assert should_retry(RuntimeError(), cfg) is True


# ---------------------------------------------------------------------------
# retry_with_backoff — success
# ---------------------------------------------------------------------------

class TestRetryWithBackoffSuccess:
    def test_immediate_success(self):
        func = AsyncMock(return_value=42)
        result = _run(retry_with_backoff(func, config=RetryConfig(max_attempts=3)))
        assert result == 42
        assert func.call_count == 1

    def test_sync_func_success(self):
        result = _run(retry_with_backoff(
            lambda: "ok",
            config=RetryConfig(max_attempts=3),
        ))
        assert result == "ok"

    def test_args_forwarded(self):
        async def add(a, b):
            return a + b

        result = _run(retry_with_backoff(add, 3, 7, config=RetryConfig()))
        assert result == 10


# ---------------------------------------------------------------------------
# retry_with_backoff — retry then succeed
# ---------------------------------------------------------------------------

class TestRetryWithBackoffRetryThenSucceed:
    def test_succeeds_after_failures(self):
        call_count = 0

        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("transient")
            return "success"

        cfg = RetryConfig(max_attempts=5, base_delay=0.001, jitter=False)
        result = _run(retry_with_backoff(flaky, config=cfg))
        assert result == "success"
        assert call_count == 3

    def test_on_retry_callback_called(self):
        call_count = 0
        retries = []

        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RuntimeError("fail")
            return "ok"

        cfg = RetryConfig(max_attempts=3, base_delay=0.001, jitter=False)
        result = _run(retry_with_backoff(
            flaky,
            config=cfg,
            on_retry=lambda attempt, exc, delay: retries.append((attempt, type(exc).__name__)),
        ))
        assert result == "ok"
        assert len(retries) == 1
        assert retries[0] == (1, "RuntimeError")


# ---------------------------------------------------------------------------
# retry_with_backoff — all retries exhausted
# ---------------------------------------------------------------------------

class TestRetryExhausted:
    def test_raises_after_max_attempts(self):
        cfg = RetryConfig(max_attempts=3, base_delay=0.001, jitter=False)
        func = AsyncMock(side_effect=ConnectionError("down"))

        with pytest.raises(ConnectionError, match="down"):
            _run(retry_with_backoff(func, config=cfg))
        assert func.call_count == 3

    def test_no_retry_exception_fails_immediately(self):
        cfg = RetryConfig(
            max_attempts=5,
            base_delay=0.001,
            no_retry_exceptions=(ValueError,),
        )
        func = AsyncMock(side_effect=ValueError("bad input"))

        with pytest.raises(ValueError, match="bad input"):
            _run(retry_with_backoff(func, config=cfg))
        assert func.call_count == 1

    def test_non_matching_exception_fails_immediately(self):
        cfg = RetryConfig(
            max_attempts=5,
            base_delay=0.001,
            retry_exceptions=(ConnectionError,),
        )
        func = AsyncMock(side_effect=TypeError("wrong type"))

        with pytest.raises(TypeError, match="wrong type"):
            _run(retry_with_backoff(func, config=cfg))
        assert func.call_count == 1


# ---------------------------------------------------------------------------
# retry decorator
# ---------------------------------------------------------------------------

class TestRetryDecorator:
    def test_async_decorator(self):
        call_count = 0

        @retry(max_attempts=3, base_delay=0.001)
        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RuntimeError("once")
            return "done"

        result = _run(flaky())
        assert result == "done"
        assert call_count == 2

    def test_decorator_with_exception_filter(self):
        @retry(
            max_attempts=5,
            base_delay=0.001,
            retry_exceptions=(ConnectionError,),
        )
        async def strict():
            raise ValueError("non-retryable")

        with pytest.raises(ValueError):
            _run(strict())

    def test_decorator_no_retry_exceptions(self):
        call_count = 0

        @retry(
            max_attempts=5,
            base_delay=0.001,
            no_retry_exceptions=(ValueError,),
        )
        async def fn():
            nonlocal call_count
            call_count += 1
            raise ValueError("stop immediately")

        with pytest.raises(ValueError):
            _run(fn())
        assert call_count == 1


# ---------------------------------------------------------------------------
# Pre-configured decorators
# ---------------------------------------------------------------------------

class TestPreConfiguredDecorators:
    def test_retry_api_call_wraps_async(self):
        @retry_api_call
        async def fetch():
            return "data"

        assert asyncio.iscoroutinefunction(fetch)

    def test_retry_database_wraps_async(self):
        @retry_database
        async def query():
            return "rows"

        assert asyncio.iscoroutinefunction(query)

    def test_retry_api_call_retries_connection_error(self):
        call_count = 0

        @retry_api_call
        async def api_call():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("timeout")
            return "ok"

        with patch("src.resilience.retry.asyncio.sleep", new_callable=AsyncMock):
            result = _run(api_call())
        assert result == "ok"
        assert call_count == 2

    def test_retry_database_retries(self):
        call_count = 0

        @retry_database
        async def db_op():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RuntimeError("lock timeout")
            return "committed"

        with patch("src.resilience.retry.asyncio.sleep", new_callable=AsyncMock):
            result = _run(db_op())
        assert result == "committed"
