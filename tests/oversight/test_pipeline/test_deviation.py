"""Tests for Sonnet deviation classifier."""

from unittest.mock import MagicMock, patch

import pytest

from src.oversight.pipeline.baseline import BaselineSummary
from src.oversight.pipeline.deviation import (
    DeviationResult,
    _get_client,
    check_deviation,
    classify_deviation_type,
)


@pytest.fixture
def sample_baseline():
    return BaselineSummary(
        source_type="gao",
        theme="healthcare",
        window_start="2025-10-01",
        window_end="2026-01-01",
        event_count=25,
        summary="Regular GAO healthcare reports covering wait times, staffing, budget",
        topic_distribution={"wait_times": 0.4, "staffing": 0.3, "budget": 0.3},
    )


@pytest.fixture
def mock_anthropic_response():
    def _create_response(content: str):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=content)]
        return mock_response

    return _create_response


def test_deviation_result_creation():
    result = DeviationResult(
        is_deviation=True,
        deviation_type="new_topic",
        confidence=0.85,
        explanation="First GAO report on AI in VA healthcare",
    )
    assert result.is_deviation is True
    assert result.deviation_type == "new_topic"


def test_get_client_uses_keychain_fallback(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    captured = {}

    def fake_get_env_or_keychain(env_var, keychain_service, **_kwargs):
        captured["env_var"] = env_var
        captured["keychain_service"] = keychain_service
        return "keychain-value"

    monkeypatch.setattr(
        "src.oversight.pipeline.deviation.get_env_or_keychain",
        fake_get_env_or_keychain,
        raising=False,
    )

    def fake_anthropic(api_key):
        captured["api_key"] = api_key
        return "client"

    monkeypatch.setattr(
        "src.oversight.pipeline.deviation.anthropic.Anthropic",
        fake_anthropic,
    )

    assert _get_client() == "client"
    assert captured["env_var"] == "ANTHROPIC_API_KEY"
    assert captured["keychain_service"] == "claude-api"
    assert captured["api_key"] == "keychain-value"


def test_deviation_result_no_deviation():
    result = DeviationResult(
        is_deviation=False,
        deviation_type=None,
        confidence=0.95,
        explanation="Routine quarterly wait times report",
    )
    assert result.is_deviation is False


@patch("src.oversight.pipeline.deviation._get_client")
def test_check_deviation_routine(mock_get_client, mock_anthropic_response, sample_baseline):
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_anthropic_response(
        '{"is_deviation": false, "deviation_type": null, "confidence": 0.9, "explanation": "Routine quarterly report on wait times"}'
    )
    mock_get_client.return_value = mock_client

    result = check_deviation(
        title="Q4 2025 VA Wait Times Report",
        content="This quarterly report examines wait times...",
        baseline=sample_baseline,
    )

    assert result.is_deviation is False


@patch("src.oversight.pipeline.deviation._get_client")
def test_check_deviation_new_topic(mock_get_client, mock_anthropic_response, sample_baseline):
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_anthropic_response(
        '{"is_deviation": true, "deviation_type": "new_topic", "confidence": 0.85, "explanation": "First report on AI systems in VA"}'
    )
    mock_get_client.return_value = mock_client

    result = check_deviation(
        title="GAO Report on AI Implementation in VA Healthcare",
        content="This report examines the deployment of artificial intelligence...",
        baseline=sample_baseline,
    )

    assert result.is_deviation is True
    assert result.deviation_type == "new_topic"


@patch("src.oversight.pipeline.deviation._get_client")
def test_check_deviation_frequency_spike(mock_get_client, mock_anthropic_response, sample_baseline):
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_anthropic_response(
        '{"is_deviation": true, "deviation_type": "frequency_spike", "confidence": 0.8, "explanation": "Unusual increase in fraud-related reports"}'
    )
    mock_get_client.return_value = mock_client

    result = check_deviation(
        title="Third GAO Fraud Investigation This Month",
        content="Another investigation into VA contracting fraud...",
        baseline=sample_baseline,
    )

    assert result.is_deviation is True
    assert result.deviation_type == "frequency_spike"


def test_classify_deviation_type():
    """Test deviation type classification."""
    # New topic
    assert (
        classify_deviation_type(
            event_topics={"ai": 0.8, "technology": 0.2},
            baseline_topics={"wait_times": 0.5, "staffing": 0.5},
        )
        == "new_topic"
    )

    # Similar topics
    assert (
        classify_deviation_type(
            event_topics={"wait_times": 0.6, "staffing": 0.4},
            baseline_topics={"wait_times": 0.5, "staffing": 0.5},
        )
        is None
    )


def test_check_deviation_missing_key_fails_closed(monkeypatch, sample_baseline):
    def raise_missing_key(*_args, **_kwargs):
        raise RuntimeError("No ANTHROPIC_API_KEY found")

    monkeypatch.setattr(
        "src.oversight.pipeline.deviation.get_env_or_keychain",
        raise_missing_key,
    )

    result = check_deviation(
        title="Q4 2025 VA Wait Times Report",
        content="This quarterly report examines wait times...",
        baseline=sample_baseline,
    )

    assert result.is_deviation is False
    assert "classification error" in result.explanation.lower()
