"""Tests for circuit breaker pattern implementation."""

import asyncio
import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from src.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpen,
    CircuitMetrics,
    CircuitState,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_cb(name: str, **config_kw) -> CircuitBreaker:
    """Create a circuit breaker with a unique name to avoid registry collisions."""
    cfg = CircuitBreakerConfig(**config_kw)
    return CircuitBreaker(name, cfg)


async def _fail_n_times(cb: CircuitBreaker, n: int, exc: Exception = None):
    """Drive *n* failures through the circuit breaker."""
    exc = exc or RuntimeError("boom")
    for _ in range(n):
        with pytest.raises(type(exc)):
            await cb.call(AsyncMock(side_effect=exc))


async def _succeed_n_times(cb: CircuitBreaker, n: int, retval=None):
    """Drive *n* successes through the circuit breaker."""
    for _ in range(n):
        result = await cb.call(AsyncMock(return_value=retval))
        assert result == retval


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# CircuitState enum
# ---------------------------------------------------------------------------


class TestCircuitState:
    def test_values(self):
        assert CircuitState.CLOSED.value == "closed"
        assert CircuitState.OPEN.value == "open"
        assert CircuitState.HALF_OPEN.value == "half_open"

    def test_is_str_enum(self):
        assert isinstance(CircuitState.CLOSED, str)


# ---------------------------------------------------------------------------
# CircuitBreakerOpen exception
# ---------------------------------------------------------------------------


class TestCircuitBreakerOpen:
    def test_attributes(self):
        until = datetime.now(UTC)
        exc = CircuitBreakerOpen("svc", until)
        assert exc.name == "svc"
        assert exc.until is until
        assert "svc" in str(exc)

    def test_is_exception(self):
        exc = CircuitBreakerOpen("x", datetime.now(UTC))
        assert isinstance(exc, Exception)


# ---------------------------------------------------------------------------
# CircuitBreakerConfig defaults
# ---------------------------------------------------------------------------


class TestCircuitBreakerConfig:
    def test_defaults(self):
        cfg = CircuitBreakerConfig()
        assert cfg.failure_threshold == 5
        assert cfg.success_threshold == 2
        assert cfg.timeout_seconds == 60.0
        assert cfg.half_open_max_calls == 3
        assert cfg.exclude_exceptions == ()
        assert cfg.include_exceptions == (Exception,)


# ---------------------------------------------------------------------------
# CircuitMetrics defaults
# ---------------------------------------------------------------------------


class TestCircuitMetrics:
    def test_defaults(self):
        m = CircuitMetrics()
        assert m.total_calls == 0
        assert m.successful_calls == 0
        assert m.failed_calls == 0
        assert m.rejected_calls == 0
        assert m.state_changes == 0
        assert m.last_failure_time is None
        assert m.last_success_time is None
        assert m.last_state_change is None
        assert m.consecutive_failures == 0
        assert m.consecutive_successes == 0


# ---------------------------------------------------------------------------
# CircuitBreaker — init / properties / registry
# ---------------------------------------------------------------------------


class TestCircuitBreakerInit:
    def test_initial_state_is_closed(self):
        cb = _fresh_cb("init_closed")
        assert cb.state == CircuitState.CLOSED

    def test_default_config(self):
        cb = CircuitBreaker("init_default_cfg")
        assert cb.config.failure_threshold == 5

    def test_custom_config(self):
        cb = _fresh_cb("init_custom", failure_threshold=10, timeout_seconds=120)
        assert cb.config.failure_threshold == 10
        assert cb.config.timeout_seconds == 120

    def test_registry_contains_instance(self):
        cb = _fresh_cb("init_registry_test")
        assert CircuitBreaker.get("init_registry_test") is cb

    def test_get_unknown_returns_none(self):
        assert CircuitBreaker.get("no_such_cb_xyz") is None

    def test_all_returns_copy(self):
        _fresh_cb("init_all_test")
        all_cbs = CircuitBreaker.all()
        assert isinstance(all_cbs, dict)
        assert "init_all_test" in all_cbs

    def test_metrics_property(self):
        cb = _fresh_cb("init_metrics")
        assert isinstance(cb.metrics, CircuitMetrics)


# ---------------------------------------------------------------------------
# CircuitBreaker — call: happy path
# ---------------------------------------------------------------------------


class TestCallHappyPath:
    def test_async_func_passes_through(self):
        cb = _fresh_cb("call_async_pass")
        result = _run(cb.call(AsyncMock(return_value=42)))
        assert result == 42
        assert cb.metrics.successful_calls == 1
        assert cb.metrics.total_calls == 1

    def test_sync_func_passes_through(self):
        cb = _fresh_cb("call_sync_pass")
        result = _run(cb.call(lambda: "ok"))
        assert result == "ok"
        assert cb.metrics.successful_calls == 1

    def test_args_kwargs_forwarded(self):
        cb = _fresh_cb("call_fwd")

        async def adder(a, b, extra=0):
            return a + b + extra

        result = _run(cb.call(adder, 1, 2, extra=10))
        assert result == 13

    def test_consecutive_successes_tracked(self):
        cb = _fresh_cb("call_consec")
        _run(_succeed_n_times(cb, 3))
        assert cb.metrics.consecutive_successes == 3
        assert cb.metrics.consecutive_failures == 0
        assert cb.metrics.last_success_time is not None


# ---------------------------------------------------------------------------
# CircuitBreaker — call: failure path
# ---------------------------------------------------------------------------


class TestCallFailurePath:
    def test_failure_is_recorded(self):
        cb = _fresh_cb("fail_rec", failure_threshold=10)
        with pytest.raises(RuntimeError):
            _run(cb.call(AsyncMock(side_effect=RuntimeError("boom"))))
        assert cb.metrics.failed_calls == 1
        assert cb.metrics.consecutive_failures == 1
        assert cb.metrics.last_failure_time is not None

    def test_failure_resets_consecutive_successes(self):
        cb = _fresh_cb("fail_reset", failure_threshold=10)
        _run(_succeed_n_times(cb, 3))
        assert cb.metrics.consecutive_successes == 3
        with pytest.raises(RuntimeError):
            _run(cb.call(AsyncMock(side_effect=RuntimeError("boom"))))
        assert cb.metrics.consecutive_successes == 0

    def test_exception_propagates(self):
        cb = _fresh_cb("fail_exc", failure_threshold=10)
        with pytest.raises(ValueError, match="special"):
            _run(cb.call(AsyncMock(side_effect=ValueError("special"))))


# ---------------------------------------------------------------------------
# State transitions: CLOSED -> OPEN
# ---------------------------------------------------------------------------


class TestClosedToOpen:
    def test_opens_at_threshold(self):
        cb = _fresh_cb("c2o_thresh", failure_threshold=3)
        _run(_fail_n_times(cb, 3))
        assert cb.state == CircuitState.OPEN
        assert cb.metrics.state_changes == 1

    def test_stays_closed_below_threshold(self):
        cb = _fresh_cb("c2o_below", failure_threshold=5)
        _run(_fail_n_times(cb, 4))
        assert cb.state == CircuitState.CLOSED

    def test_rejects_when_open(self):
        cb = _fresh_cb("c2o_reject", failure_threshold=2, timeout_seconds=9999)
        _run(_fail_n_times(cb, 2))
        assert cb.state == CircuitState.OPEN
        with pytest.raises(CircuitBreakerOpen) as exc_info:
            _run(cb.call(AsyncMock(return_value=1)))
        assert exc_info.value.name == "c2o_reject"
        assert cb.metrics.rejected_calls == 1


# ---------------------------------------------------------------------------
# State transitions: OPEN -> HALF_OPEN (timeout elapsed)
# ---------------------------------------------------------------------------


class TestOpenToHalfOpen:
    def test_transitions_after_timeout(self):
        cb = _fresh_cb("o2ho", failure_threshold=2, timeout_seconds=0.05)
        _run(_fail_n_times(cb, 2))
        assert cb.state == CircuitState.OPEN

        time.sleep(0.1)  # Wait past timeout

        # Next call triggers state check and transitions to HALF_OPEN
        result = _run(cb.call(AsyncMock(return_value="recovered")))
        assert result == "recovered"


# ---------------------------------------------------------------------------
# State transitions: HALF_OPEN -> CLOSED (enough successes)
# ---------------------------------------------------------------------------


class TestHalfOpenToClosed:
    def test_closes_after_success_threshold(self):
        cb = _fresh_cb(
            "ho2c",
            failure_threshold=2,
            success_threshold=2,
            timeout_seconds=0.01,
        )
        _run(_fail_n_times(cb, 2))
        assert cb.state == CircuitState.OPEN

        time.sleep(0.05)

        # Drive enough successes to close
        _run(_succeed_n_times(cb, 2, retval="ok"))
        assert cb.state == CircuitState.CLOSED
        assert cb.metrics.consecutive_failures == 0


# ---------------------------------------------------------------------------
# State transitions: HALF_OPEN -> OPEN (failure in half-open)
# ---------------------------------------------------------------------------


class TestHalfOpenToOpen:
    def test_reopens_on_failure(self):
        cb = _fresh_cb(
            "ho2o",
            failure_threshold=2,
            timeout_seconds=0.01,
        )
        _run(_fail_n_times(cb, 2))
        assert cb.state == CircuitState.OPEN

        time.sleep(0.05)

        # Fail in half-open -> back to OPEN
        with pytest.raises(RuntimeError):
            _run(cb.call(AsyncMock(side_effect=RuntimeError("still broken"))))
        assert cb.state == CircuitState.OPEN


# ---------------------------------------------------------------------------
# HALF_OPEN max calls limit
# ---------------------------------------------------------------------------


class TestHalfOpenMaxCalls:
    def test_rejects_excess_half_open_calls(self):
        cb = _fresh_cb(
            "ho_max",
            failure_threshold=1,
            timeout_seconds=0.01,
            half_open_max_calls=1,
            success_threshold=5,
        )
        # Open the circuit
        _run(_fail_n_times(cb, 1))
        assert cb.state == CircuitState.OPEN

        time.sleep(0.05)

        # First call in half-open -- succeeds, uses up the 1 allowed call
        _run(cb.call(AsyncMock(return_value="test")))

        # Second call should be rejected (half_open_max_calls=1)
        with pytest.raises(CircuitBreakerOpen):
            _run(cb.call(AsyncMock(return_value="excess")))
        assert cb.metrics.rejected_calls >= 1


# ---------------------------------------------------------------------------
# _should_count_failure
# ---------------------------------------------------------------------------


class TestShouldCountFailure:
    def test_included_exception_counts(self):
        cb = _fresh_cb("scf_incl")
        assert cb._should_count_failure(ValueError("x")) is True

    def test_excluded_exception_does_not_count(self):
        cb = _fresh_cb(
            "scf_excl",
            exclude_exceptions=(KeyError,),
        )
        assert cb._should_count_failure(KeyError("x")) is False

    def test_non_included_exception_does_not_count(self):
        cb = _fresh_cb(
            "scf_noincl",
            include_exceptions=(ValueError,),
        )
        assert cb._should_count_failure(TypeError("x")) is False

    def test_excluded_exception_not_counted_during_call(self):
        cb = _fresh_cb(
            "scf_call_excl",
            failure_threshold=1,
            exclude_exceptions=(KeyError,),
        )
        with pytest.raises(KeyError):
            _run(cb.call(AsyncMock(side_effect=KeyError("ignored"))))
        # Should NOT have opened since KeyError is excluded
        assert cb.state == CircuitState.CLOSED
        assert cb.metrics.failed_calls == 0

    def test_include_filter_limits_counted_failures(self):
        cb = _fresh_cb(
            "scf_incl_filter",
            failure_threshold=1,
            include_exceptions=(ConnectionError,),
        )
        # TypeError is NOT in include list, so should not trip breaker
        with pytest.raises(TypeError):
            _run(cb.call(AsyncMock(side_effect=TypeError("not counted"))))
        assert cb.state == CircuitState.CLOSED

        # ConnectionError IS in include list
        with pytest.raises(ConnectionError):
            _run(cb.call(AsyncMock(side_effect=ConnectionError("counted"))))
        assert cb.state == CircuitState.OPEN


# ---------------------------------------------------------------------------
# Decorator usage
# ---------------------------------------------------------------------------


class TestDecorator:
    def test_async_decorator(self):
        cb = _fresh_cb("dec_async", failure_threshold=5)

        @cb
        async def my_func(x):
            return x * 2

        result = _run(my_func(5))
        assert result == 10
        assert cb.metrics.successful_calls == 1

    def test_async_decorator_failure(self):
        cb = _fresh_cb("dec_async_fail", failure_threshold=1)

        @cb
        async def failing():
            raise RuntimeError("nope")

        with pytest.raises(RuntimeError):
            _run(failing())
        assert cb.state == CircuitState.OPEN


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------


class TestReset:
    def test_reset_from_open(self):
        cb = _fresh_cb("reset_open", failure_threshold=1)
        _run(_fail_n_times(cb, 1))
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.metrics.consecutive_failures == 0
        assert cb.metrics.consecutive_successes == 0

    def test_can_call_after_reset(self):
        cb = _fresh_cb("reset_call", failure_threshold=1, timeout_seconds=9999)
        _run(_fail_n_times(cb, 1))
        cb.reset()
        result = _run(cb.call(AsyncMock(return_value="back")))
        assert result == "back"


# ---------------------------------------------------------------------------
# to_dict
# ---------------------------------------------------------------------------


class TestToDict:
    def test_dict_keys(self):
        cb = _fresh_cb("to_dict_keys", failure_threshold=3)
        _run(_succeed_n_times(cb, 2))
        d = cb.to_dict()
        assert d["name"] == "to_dict_keys"
        assert d["state"] == "closed"
        assert d["metrics"]["total_calls"] == 2
        assert d["metrics"]["successful_calls"] == 2
        assert d["config"]["failure_threshold"] == 3
        assert d["opened_at"] is None

    def test_dict_when_open(self):
        cb = _fresh_cb("to_dict_open", failure_threshold=1)
        _run(_fail_n_times(cb, 1))
        d = cb.to_dict()
        assert d["state"] == "open"
        assert d["opened_at"] is not None


# ---------------------------------------------------------------------------
# Pre-configured instances (module level)
# ---------------------------------------------------------------------------


class TestPreConfigured:
    def test_federal_register_cb_exists(self):
        from src.resilience.circuit_breaker import federal_register_cb

        assert federal_register_cb.name == "federal_register"
        assert federal_register_cb.config.failure_threshold == 3

    def test_congress_api_cb_exists(self):
        from src.resilience.circuit_breaker import congress_api_cb

        assert congress_api_cb.name == "congress_api"

    def test_database_cb_exists(self):
        from src.resilience.circuit_breaker import database_cb

        assert database_cb.name == "database"
        assert database_cb.config.timeout_seconds == 30
