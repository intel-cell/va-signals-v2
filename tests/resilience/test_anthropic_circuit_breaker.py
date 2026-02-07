"""Tests for Anthropic API circuit breaker integration."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from src.resilience.circuit_breaker import (
    CircuitBreakerOpen,
    CircuitState,
    anthropic_cb,
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
# Pre-configured anthropic_cb instance
# ---------------------------------------------------------------------------


class TestAnthropicCBExists:
    def test_registered_in_registry(self):
        from src.resilience.circuit_breaker import CircuitBreaker

        assert CircuitBreaker.get("anthropic") is anthropic_cb

    def test_name(self):
        assert anthropic_cb.name == "anthropic"

    def test_failure_threshold(self):
        assert anthropic_cb.config.failure_threshold == 5

    def test_recovery_timeout(self):
        assert anthropic_cb.config.timeout_seconds == 60


# ---------------------------------------------------------------------------
# summarize._post_anthropic wrapped with circuit breaker
# ---------------------------------------------------------------------------


class TestSummarizeCircuitBreaker:
    def setup_method(self):
        """Reset the anthropic circuit breaker before each test."""
        anthropic_cb.reset()

    @patch("src.summarize.requests.post")
    def test_successful_call_passes_through(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"content": [{"text": '{"summary": "test"}'}]}
        mock_post.return_value = mock_resp

        from src.summarize import _post_anthropic

        result = _post_anthropic({}, {}, 30)
        assert result is mock_resp

    @patch("src.summarize.requests.post")
    def test_circuit_opens_after_failures(self, mock_post):
        import requests

        mock_post.side_effect = requests.exceptions.ConnectionError("API down")

        from src.summarize import _post_anthropic

        # Drive failures up to threshold
        for _ in range(5):
            with pytest.raises(requests.exceptions.ConnectionError):
                _post_anthropic({}, {}, 30)

        # Now circuit should be open
        assert anthropic_cb.state == CircuitState.OPEN

        # Next call should fail fast with CircuitBreakerOpen
        with pytest.raises(CircuitBreakerOpen):
            _post_anthropic({}, {}, 30)

    @patch("src.summarize.requests.post")
    def test_call_claude_returns_none_when_circuit_open(self, mock_post):
        import requests

        mock_post.side_effect = requests.exceptions.ConnectionError("API down")

        from src.summarize import _call_claude

        # Drive failures to open the circuit
        for _ in range(5):
            _call_claude("sys", "user", "fake-key", timeout=5, retries=0)

        assert anthropic_cb.state == CircuitState.OPEN

        # _call_claude should return None (fail gracefully) when circuit is open
        result = _call_claude("sys", "user", "fake-key", timeout=5, retries=0)
        assert result is None


# ---------------------------------------------------------------------------
# classifier._call_haiku wrapped with circuit breaker
# ---------------------------------------------------------------------------


class TestClassifierCircuitBreaker:
    def setup_method(self):
        anthropic_cb.reset()

    @patch("src.oversight.pipeline.classifier._get_client")
    def test_is_va_relevant_fails_open_when_circuit_open(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = RuntimeError("API down")
        mock_get_client.return_value = mock_client

        from src.oversight.pipeline.classifier import is_va_relevant

        # Drive 5 failures to open circuit
        for _ in range(5):
            is_va_relevant("test", "content")

        assert anthropic_cb.state == CircuitState.OPEN

        # When circuit is open, should fail open (assume relevant)
        result = is_va_relevant("test", "content")
        assert result["is_va_relevant"] is True
        assert (
            "circuit breaker" in result["explanation"].lower()
            or "Circuit breaker" in result["explanation"]
        )

    @patch("src.oversight.pipeline.classifier._get_client")
    def test_is_dated_action_fails_open_when_circuit_open(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = RuntimeError("API down")
        mock_get_client.return_value = mock_client

        from src.oversight.pipeline.classifier import is_dated_action

        # Drive 5 failures to open circuit
        for _ in range(5):
            is_dated_action("test", "content")

        assert anthropic_cb.state == CircuitState.OPEN

        result = is_dated_action("test", "content")
        assert result["is_dated_action"] is True


# ---------------------------------------------------------------------------
# deviation._call_sonnet wrapped with circuit breaker
# ---------------------------------------------------------------------------


class TestDeviationCircuitBreaker:
    def setup_method(self):
        anthropic_cb.reset()

    @patch("src.oversight.pipeline.deviation._get_client")
    def test_check_deviation_fails_closed_when_circuit_open(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = RuntimeError("API down")
        mock_get_client.return_value = mock_client

        from src.oversight.pipeline.deviation import BaselineSummary, check_deviation

        baseline = BaselineSummary(
            source_type="test",
            theme=None,
            window_start="2024-01-01",
            window_end="2024-02-01",
            event_count=10,
            summary="test baseline",
            topic_distribution={"topic_a": 0.5},
        )

        # Drive 5 failures to open circuit
        for _ in range(5):
            check_deviation("test", "content", baseline)

        assert anthropic_cb.state == CircuitState.OPEN

        # When circuit is open, should fail closed (don't flag as deviation)
        result = check_deviation("test", "content", baseline)
        assert result.is_deviation is False
        assert (
            "circuit breaker" in result.explanation.lower()
            or "Circuit breaker" in result.explanation
        )


# ---------------------------------------------------------------------------
# state/classify._call_haiku wrapped with circuit breaker
# ---------------------------------------------------------------------------


class TestStateClassifyCircuitBreaker:
    def setup_method(self):
        anthropic_cb.reset()

    @patch("src.state.classify._get_api_key", return_value="fake-key")
    @patch("anthropic.Anthropic")
    def test_classify_by_llm_falls_back_to_keywords_when_circuit_open(
        self, mock_anthropic_cls, mock_key
    ):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = RuntimeError("API down")
        mock_anthropic_cls.return_value = mock_client

        from src.state.classify import classify_by_llm

        # Drive 5 failures to open circuit
        for _ in range(5):
            classify_by_llm("VA healthcare suspended", None, "TX")

        assert anthropic_cb.state == CircuitState.OPEN

        # When circuit is open, should fall back to keyword classification
        result = classify_by_llm("VA healthcare suspended", None, "TX")
        assert result.method == "keyword"


# ---------------------------------------------------------------------------
# Shared circuit breaker across modules
# ---------------------------------------------------------------------------


class TestSharedCircuitBreaker:
    """All LLM call sites share the same anthropic_cb instance."""

    def setup_method(self):
        anthropic_cb.reset()

    @patch("src.summarize.requests.post")
    @patch("src.oversight.pipeline.classifier._get_client")
    def test_failures_in_one_module_open_circuit_for_all(self, mock_get_client, mock_post):
        import requests

        # Fail through summarize module
        mock_post.side_effect = requests.exceptions.ConnectionError("down")
        from src.summarize import _call_claude

        for _ in range(5):
            _call_claude("sys", "user", "fake-key", timeout=5, retries=0)

        assert anthropic_cb.state == CircuitState.OPEN

        # Classifier should also see the open circuit
        mock_client = MagicMock()
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text='{"is_va_relevant": true, "explanation": "ok"}')]
        )
        mock_get_client.return_value = mock_client

        from src.oversight.pipeline.classifier import is_va_relevant

        result = is_va_relevant("test", "content")
        # Should get circuit breaker open response, not call the API
        assert (
            "circuit breaker" in result["explanation"].lower()
            or "Circuit breaker" in result["explanation"]
        )
