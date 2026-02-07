"""Tests for sync-friendly resilience wiring decorators."""

import signal
import time

import pytest

from src.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpen,
    CircuitState,
)
from src.resilience.rate_limiter import RateLimiter
from src.resilience.wiring import (
    GLOBAL_HTTP_TIMEOUT,
    FetchTimeout,
    circuit_breaker_sync,
    with_timeout,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_cb(name: str, **config_kw) -> CircuitBreaker:
    """Create a circuit breaker with a unique name to avoid registry collisions."""
    cfg = CircuitBreakerConfig(**config_kw)
    return CircuitBreaker(name, cfg)


# ---------------------------------------------------------------------------
# circuit_breaker_sync: happy path
# ---------------------------------------------------------------------------


class TestCircuitBreakerSyncHappyPath:
    def test_passes_through_on_success(self):
        cb = _fresh_cb("sync_pass")

        @circuit_breaker_sync(cb)
        def good_func():
            return 42

        assert good_func() == 42
        assert cb.metrics.successful_calls == 1

    def test_forwards_args_and_kwargs(self):
        cb = _fresh_cb("sync_args")

        @circuit_breaker_sync(cb)
        def adder(a, b, extra=0):
            return a + b + extra

        assert adder(1, 2, extra=10) == 13

    def test_consecutive_successes_tracked(self):
        cb = _fresh_cb("sync_consec")

        @circuit_breaker_sync(cb)
        def ok():
            return "ok"

        for _ in range(3):
            ok()
        assert cb.metrics.successful_calls == 3


# ---------------------------------------------------------------------------
# circuit_breaker_sync: failure path
# ---------------------------------------------------------------------------


class TestCircuitBreakerSyncFailurePath:
    def test_failure_is_recorded(self):
        cb = _fresh_cb("sync_fail_rec", failure_threshold=10)

        @circuit_breaker_sync(cb)
        def bad():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            bad()
        assert cb.metrics.failed_calls == 1

    def test_exception_propagates(self):
        cb = _fresh_cb("sync_fail_exc", failure_threshold=10)

        @circuit_breaker_sync(cb)
        def special():
            raise ValueError("special")

        with pytest.raises(ValueError, match="special"):
            special()


# ---------------------------------------------------------------------------
# circuit_breaker_sync: trips after N failures
# ---------------------------------------------------------------------------


class TestCircuitBreakerSyncTrips:
    def test_opens_after_threshold(self):
        cb = _fresh_cb("sync_trip", failure_threshold=3, timeout_seconds=9999)

        @circuit_breaker_sync(cb)
        def failing():
            raise RuntimeError("fail")

        # Drive 3 failures to trip the breaker
        for _ in range(3):
            with pytest.raises(RuntimeError):
                failing()

        assert cb.state == CircuitState.OPEN

    def test_rejects_calls_when_open(self):
        cb = _fresh_cb("sync_reject", failure_threshold=2, timeout_seconds=9999)

        call_count = 0

        @circuit_breaker_sync(cb)
        def failing():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("fail")

        # Trip the breaker
        for _ in range(2):
            with pytest.raises(RuntimeError):
                failing()

        assert cb.state == CircuitState.OPEN
        assert call_count == 2

        # Next call should be rejected without calling the function
        with pytest.raises(CircuitBreakerOpen) as exc_info:
            failing()
        assert exc_info.value.name == "sync_reject"
        assert call_count == 2  # Function was NOT called
        assert cb.metrics.rejected_calls >= 1

    def test_recovers_after_timeout(self):
        cb = _fresh_cb("sync_recover", failure_threshold=2, timeout_seconds=0.05)

        call_count = 0

        @circuit_breaker_sync(cb)
        def func():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise RuntimeError("fail")
            return "recovered"

        # Trip the breaker
        for _ in range(2):
            with pytest.raises(RuntimeError):
                func()
        assert cb.state == CircuitState.OPEN

        # Wait for timeout
        time.sleep(0.1)

        # Should transition to half-open and allow the call
        result = func()
        assert result == "recovered"

    def test_excluded_exception_does_not_trip(self):
        cb = _fresh_cb(
            "sync_excl",
            failure_threshold=1,
            exclude_exceptions=(KeyError,),
        )

        @circuit_breaker_sync(cb)
        def raising_key():
            raise KeyError("ignored")

        with pytest.raises(KeyError):
            raising_key()
        # KeyError is excluded, so breaker should stay CLOSED
        assert cb.state == CircuitState.CLOSED
        assert cb.metrics.failed_calls == 0


# ---------------------------------------------------------------------------
# with_timeout: enforcement
# ---------------------------------------------------------------------------


class TestWithTimeout:
    def test_fast_function_completes(self):
        @with_timeout(5, name="fast")
        def fast():
            return "done"

        assert fast() == "done"

    def test_timeout_raises_fetch_timeout(self):
        @with_timeout(1, name="slow_test")
        def slow():
            time.sleep(10)
            return "never"

        with pytest.raises(FetchTimeout) as exc_info:
            slow()
        assert exc_info.value.name == "slow_test"
        assert exc_info.value.timeout == 1

    def test_timeout_restores_old_handler(self):
        original_handler = signal.getsignal(signal.SIGALRM)

        @with_timeout(5, name="restore_test")
        def fast():
            return "ok"

        fast()
        assert signal.getsignal(signal.SIGALRM) == original_handler

    def test_global_timeout_is_45(self):
        assert GLOBAL_HTTP_TIMEOUT == 45

    def test_default_timeout_is_global(self):
        """with_timeout() without args uses GLOBAL_HTTP_TIMEOUT."""

        @with_timeout()
        def func():
            return True

        assert func()


# ---------------------------------------------------------------------------
# FetchTimeout exception
# ---------------------------------------------------------------------------


class TestFetchTimeout:
    def test_attributes(self):
        exc = FetchTimeout("test_fetch", 30.0)
        assert exc.name == "test_fetch"
        assert exc.timeout == 30.0
        assert "test_fetch" in str(exc)
        assert "30" in str(exc)

    def test_is_exception(self):
        exc = FetchTimeout("x", 1.0)
        assert isinstance(exc, Exception)


# ---------------------------------------------------------------------------
# circuit_breaker_sync + with_timeout combined
# ---------------------------------------------------------------------------


class TestCombinedDecorators:
    def test_timeout_counts_as_circuit_breaker_failure(self):
        """Timeout errors should be recorded as circuit breaker failures."""
        cb = _fresh_cb("sync_combined_timeout", failure_threshold=2, timeout_seconds=9999)

        @with_timeout(1, name="combined")
        @circuit_breaker_sync(cb)
        def slow():
            time.sleep(10)
            return "never"

        with pytest.raises(FetchTimeout):
            slow()
        assert cb.metrics.failed_calls == 1

    def test_timeout_trips_breaker(self):
        """Multiple timeouts should trip the circuit breaker."""
        cb = _fresh_cb("sync_combo_trip", failure_threshold=2, timeout_seconds=9999)

        @with_timeout(1, name="combo_trip")
        @circuit_breaker_sync(cb)
        def slow():
            time.sleep(10)
            return "never"

        for _ in range(2):
            with pytest.raises(FetchTimeout):
                slow()

        assert cb.state == CircuitState.OPEN

        # Next call should be rejected immediately (no timeout)
        with pytest.raises(CircuitBreakerOpen):
            slow()


# ---------------------------------------------------------------------------
# Rate limiter throttling
# ---------------------------------------------------------------------------


class TestRateLimiterThrottling:
    def test_allows_within_burst(self):
        limiter = RateLimiter(rate=10, burst=5, name="test_burst")
        for _ in range(5):
            assert limiter.allow() is True

    def test_denies_when_exhausted(self):
        limiter = RateLimiter(rate=10, burst=3, name="test_deny")
        # Exhaust the burst
        for _ in range(3):
            limiter.allow()
        # Next call should be denied
        assert limiter.allow() is False

    def test_tracks_allowed_denied_counts(self):
        limiter = RateLimiter(rate=10, burst=2, name="test_counts")
        limiter.allow()
        limiter.allow()
        limiter.allow()  # denied
        assert limiter._state.total_allowed == 2
        assert limiter._state.total_denied == 1

    def test_refills_over_time(self):
        limiter = RateLimiter(rate=100, burst=1, name="test_refill")
        assert limiter.allow() is True
        assert limiter.allow() is False
        # Wait for refill
        time.sleep(0.05)
        assert limiter.allow() is True

    def test_retry_after(self):
        limiter = RateLimiter(rate=10, burst=1, name="test_retry_after")
        limiter.allow()  # Exhaust
        retry = limiter.retry_after()
        assert retry > 0
        assert retry <= 0.2  # Should be around 0.1s for rate=10


# ---------------------------------------------------------------------------
# Pre-configured circuit breaker instances
# ---------------------------------------------------------------------------


class TestPreConfiguredInstances:
    def test_lda_gov_cb(self):
        from src.resilience.circuit_breaker import lda_gov_cb

        assert lda_gov_cb.name == "lda_gov"
        assert lda_gov_cb.config.failure_threshold == 3

    def test_whitehouse_cb(self):
        from src.resilience.circuit_breaker import whitehouse_cb

        assert whitehouse_cb.name == "whitehouse"
        assert whitehouse_cb.config.failure_threshold == 3

    def test_omb_cb(self):
        from src.resilience.circuit_breaker import omb_cb

        assert omb_cb.name == "omb"

    def test_va_pubs_cb(self):
        from src.resilience.circuit_breaker import va_pubs_cb

        assert va_pubs_cb.name == "va_pubs"

    def test_reginfo_cb(self):
        from src.resilience.circuit_breaker import reginfo_cb

        assert reginfo_cb.name == "reginfo"

    def test_oversight_cb(self):
        from src.resilience.circuit_breaker import oversight_cb

        assert oversight_cb.name == "oversight"
        assert oversight_cb.config.failure_threshold == 5

    def test_newsapi_cb(self):
        from src.resilience.circuit_breaker import newsapi_cb

        assert newsapi_cb.name == "newsapi"

    def test_external_api_limiter(self):
        from src.resilience.rate_limiter import external_api_limiter

        assert external_api_limiter.config.name == "external"
        assert external_api_limiter.config.rate == 10
        assert external_api_limiter.config.burst == 20
