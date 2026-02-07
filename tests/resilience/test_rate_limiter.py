"""Tests for rate limiter implementation."""

import asyncio
import time

import pytest

from src.resilience.rate_limiter import (
    RateLimiter,
    RateLimiterConfig,
    RateLimiterState,
    RateLimitExceeded,
    _RateLimitAcquireContext,
)


def _run(coro):
    """Run an async coroutine synchronously, safe even if an event loop is already running."""
    try:
        asyncio.get_running_loop()
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_limiter(name: str, rate: float = 10.0, burst: int = 10) -> RateLimiter:
    """Create a rate limiter with a unique name."""
    return RateLimiter(rate=rate, burst=burst, name=name)


# ---------------------------------------------------------------------------
# RateLimitExceeded
# ---------------------------------------------------------------------------


class TestRateLimitExceeded:
    def test_attributes(self):
        exc = RateLimitExceeded("api", 1.5)
        assert exc.name == "api"
        assert exc.retry_after == 1.5
        assert "api" in str(exc)
        assert "1.5" in str(exc)

    def test_is_exception(self):
        assert isinstance(RateLimitExceeded("x", 0), Exception)


# ---------------------------------------------------------------------------
# RateLimiterConfig
# ---------------------------------------------------------------------------


class TestRateLimiterConfig:
    def test_required_fields(self):
        cfg = RateLimiterConfig(rate=5.0, burst=10, name="test")
        assert cfg.rate == 5.0
        assert cfg.burst == 10
        assert cfg.name == "test"

    def test_default_name(self):
        cfg = RateLimiterConfig(rate=1.0, burst=1)
        assert cfg.name == "default"


# ---------------------------------------------------------------------------
# RateLimiterState
# ---------------------------------------------------------------------------


class TestRateLimiterState:
    def test_fields(self):
        s = RateLimiterState(tokens=5.0, last_update=1000.0)
        assert s.tokens == 5.0
        assert s.last_update == 1000.0
        assert s.total_allowed == 0
        assert s.total_denied == 0


# ---------------------------------------------------------------------------
# RateLimiter — init / registry
# ---------------------------------------------------------------------------


class TestRateLimiterInit:
    def test_initial_tokens_equal_burst(self):
        rl = _fresh_limiter("init_tokens", rate=5, burst=20)
        assert rl._state.tokens == 20.0

    def test_registry(self):
        rl = _fresh_limiter("init_reg")
        assert RateLimiter.get("init_reg") is rl

    def test_get_unknown_returns_none(self):
        assert RateLimiter.get("no_such_limiter_xyz") is None

    def test_all_returns_copy(self):
        _fresh_limiter("init_all")
        all_rl = RateLimiter.all()
        assert isinstance(all_rl, dict)
        assert "init_all" in all_rl


# ---------------------------------------------------------------------------
# RateLimiter.allow — basic token consumption
# ---------------------------------------------------------------------------


class TestAllow:
    def test_allow_single_token(self):
        rl = _fresh_limiter("allow_single", rate=10, burst=5)
        assert rl.allow() is True
        assert rl._state.total_allowed == 1

    def test_allow_custom_tokens(self):
        rl = _fresh_limiter("allow_custom", rate=10, burst=5)
        assert rl.allow(tokens=3.0) is True
        assert rl._state.total_allowed == 1

    def test_deny_when_insufficient(self):
        rl = _fresh_limiter("allow_deny", rate=10, burst=2)
        assert rl.allow(tokens=3.0) is False
        assert rl._state.total_denied == 1

    def test_drain_bucket(self):
        rl = _fresh_limiter("allow_drain", rate=0.001, burst=3)
        assert rl.allow() is True
        assert rl.allow() is True
        assert rl.allow() is True
        assert rl.allow() is False  # Bucket drained, refill rate very slow

    def test_allow_tracks_totals(self):
        rl = _fresh_limiter("allow_totals", rate=0.001, burst=2)
        rl.allow()
        rl.allow()
        rl.allow()  # denied
        assert rl._state.total_allowed == 2
        assert rl._state.total_denied == 1


# ---------------------------------------------------------------------------
# RateLimiter.allow_async
# ---------------------------------------------------------------------------


class TestAllowAsync:
    def test_allow_async(self):
        rl = _fresh_limiter("allow_async_ok", rate=10, burst=5)
        assert _run(rl.allow_async()) is True
        assert rl._state.total_allowed == 1

    def test_deny_async(self):
        rl = _fresh_limiter("allow_async_deny", rate=0.001, burst=1)
        assert _run(rl.allow_async()) is True
        assert _run(rl.allow_async()) is False


# ---------------------------------------------------------------------------
# _refill — token replenishment
# ---------------------------------------------------------------------------


class TestRefill:
    def test_refill_adds_tokens(self):
        rl = _fresh_limiter("refill_add", rate=100, burst=10)
        rl._state.tokens = 0.0
        rl._state.last_update = time.time() - 0.1  # 0.1s ago
        rl._refill()
        assert rl._state.tokens >= 5.0  # conservative due to timing

    def test_refill_capped_at_burst(self):
        rl = _fresh_limiter("refill_cap", rate=1000, burst=5)
        rl._state.tokens = 0.0
        rl._state.last_update = time.time() - 10.0
        rl._refill()
        assert rl._state.tokens == 5.0  # capped at burst

    def test_refill_no_change_when_full(self):
        rl = _fresh_limiter("refill_full", rate=10, burst=10)
        rl._state.last_update = time.time()
        rl._refill()
        assert rl._state.tokens <= 10.0


# ---------------------------------------------------------------------------
# retry_after
# ---------------------------------------------------------------------------


class TestRetryAfter:
    def test_zero_when_tokens_available(self):
        rl = _fresh_limiter("retry_zero", rate=10, burst=5)
        assert rl.retry_after() == 0.0

    def test_positive_when_empty(self):
        rl = _fresh_limiter("retry_pos", rate=10, burst=5)
        rl._state.tokens = 0.5
        wait = rl.retry_after()
        assert 0.04 <= wait <= 0.06

    def test_zero_when_exactly_one(self):
        rl = _fresh_limiter("retry_exact", rate=10, burst=5)
        rl._state.tokens = 1.0
        assert rl.retry_after() == 0.0


# ---------------------------------------------------------------------------
# available_tokens property
# ---------------------------------------------------------------------------


class TestAvailableTokens:
    def test_returns_current_after_refill(self):
        rl = _fresh_limiter("avail_tok", rate=10, burst=10)
        tokens = rl.available_tokens
        assert 0 <= tokens <= 10.0

    def test_decreases_after_allow(self):
        rl = _fresh_limiter("avail_dec", rate=0.001, burst=10)
        before = rl.available_tokens
        rl.allow(tokens=3)
        after = rl.available_tokens
        assert after < before


# ---------------------------------------------------------------------------
# acquire — async context manager
# ---------------------------------------------------------------------------


class TestAcquire:
    def test_acquire_when_tokens_available(self):
        rl = _fresh_limiter("acq_ok", rate=10, burst=5)

        async def _do():
            ctx = await rl.acquire(tokens=1.0, timeout=1.0)
            async with ctx:
                pass  # should not raise

        _run(_do())

    def test_acquire_timeout_raises(self):
        rl = _fresh_limiter("acq_timeout", rate=0.001, burst=1)
        rl._state.tokens = 0.0

        async def _do():
            ctx = await rl.acquire(tokens=1.0, timeout=0.05)
            async with ctx:
                pass

        with pytest.raises(RateLimitExceeded):
            _run(_do())

    def test_acquire_waits_for_refill(self):
        rl = _fresh_limiter("acq_wait", rate=100, burst=5)
        rl._state.tokens = 0.0
        rl._state.last_update = time.time()

        async def _do():
            ctx = await rl.acquire(tokens=1.0, timeout=1.0)
            async with ctx:
                pass

        _run(_do())


# ---------------------------------------------------------------------------
# _RateLimitAcquireContext
# ---------------------------------------------------------------------------


class TestRateLimitAcquireContext:
    def test_aexit_is_noop(self):
        rl = _fresh_limiter("ctx_aexit", rate=10, burst=5)
        ctx = _RateLimitAcquireContext(rl, 1.0, 1.0)
        _run(ctx.__aexit__(None, None, None))  # should not raise


# ---------------------------------------------------------------------------
# to_dict
# ---------------------------------------------------------------------------


class TestToDict:
    def test_dict_keys(self):
        rl = _fresh_limiter("dict_keys", rate=10, burst=5)
        rl.allow()
        d = rl.to_dict()
        assert d["name"] == "dict_keys"
        assert d["rate"] == 10
        assert d["burst"] == 5
        assert d["total_allowed"] == 1
        assert d["total_denied"] == 0
        assert "available_tokens" in d

    def test_dict_after_deny(self):
        rl = _fresh_limiter("dict_deny", rate=0.001, burst=1)
        rl.allow()
        rl.allow()  # denied
        d = rl.to_dict()
        assert d["total_denied"] == 1


# ---------------------------------------------------------------------------
# Pre-configured instances
# ---------------------------------------------------------------------------


class TestPreConfigured:
    def test_api_rate_limiter(self):
        from src.resilience.rate_limiter import api_rate_limiter

        assert api_rate_limiter.config.rate == 100
        assert api_rate_limiter.config.burst == 200

    def test_external_api_limiter(self):
        from src.resilience.rate_limiter import external_api_limiter

        assert external_api_limiter.config.rate == 10

    def test_federal_register_limiter(self):
        from src.resilience.rate_limiter import federal_register_limiter

        assert federal_register_limiter.config.rate == 5

    def test_congress_api_limiter(self):
        from src.resilience.rate_limiter import congress_api_limiter

        assert congress_api_limiter.config.rate == 10
        assert congress_api_limiter.config.burst == 20
