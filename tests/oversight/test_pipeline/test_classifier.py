"""Tests for Haiku pre-filter classifier."""

from unittest.mock import MagicMock, patch

import pytest

from src.oversight.pipeline.classifier import (
    ClassificationResult,
    _get_client,
    classify_event,
    is_dated_action,
    is_va_relevant,
)


@pytest.fixture
def mock_anthropic_response():
    """Create a mock Anthropic API response."""

    def _create_response(content: str):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=content)]
        return mock_response

    return _create_response


def test_classification_result_creation():
    result = ClassificationResult(
        is_va_relevant=True,
        is_dated_action=True,
        rejection_reason=None,
        routine_explanation=None,
    )
    assert result.is_va_relevant is True
    assert result.is_dated_action is True
    assert result.should_process is True


def test_get_client_uses_keychain_fallback(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    captured = {}

    def fake_get_env_or_keychain(env_var, keychain_service, **_kwargs):
        captured["env_var"] = env_var
        captured["keychain_service"] = keychain_service
        return "keychain-value"

    monkeypatch.setattr(
        "src.oversight.pipeline.classifier.get_env_or_keychain",
        fake_get_env_or_keychain,
        raising=False,
    )

    def fake_anthropic(api_key):
        captured["api_key"] = api_key
        return "client"

    monkeypatch.setattr(
        "src.oversight.pipeline.classifier.anthropic.Anthropic",
        fake_anthropic,
    )

    assert _get_client() == "client"
    assert captured["env_var"] == "ANTHROPIC_API_KEY"
    assert captured["keychain_service"] == "claude-api"
    assert captured["api_key"] == "keychain-value"


def test_classification_result_rejection():
    result = ClassificationResult(
        is_va_relevant=False,
        is_dated_action=True,
        rejection_reason="not_va_relevant",
        routine_explanation="Article about DOD budget",
    )
    assert result.should_process is False


@patch("src.oversight.pipeline.classifier._get_client")
def test_is_va_relevant_true(mock_get_client, mock_anthropic_response):
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_anthropic_response(
        '{"is_va_relevant": true, "explanation": "Report about VA healthcare"}'
    )
    mock_get_client.return_value = mock_client

    result = is_va_relevant(
        title="GAO Report on VA Healthcare Wait Times",
        content="This report examines wait times at VA medical centers...",
    )

    assert result["is_va_relevant"] is True


@patch("src.oversight.pipeline.classifier._get_client")
def test_is_va_relevant_false(mock_get_client, mock_anthropic_response):
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_anthropic_response(
        '{"is_va_relevant": false, "explanation": "Report about DOD equipment"}'
    )
    mock_get_client.return_value = mock_client

    result = is_va_relevant(
        title="DOD Equipment Procurement Review",
        content="This report examines DOD equipment procurement...",
    )

    assert result["is_va_relevant"] is False


@patch("src.oversight.pipeline.classifier._get_client")
def test_is_dated_action_true(mock_get_client, mock_anthropic_response):
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_anthropic_response(
        '{"is_dated_action": true, "explanation": "New investigation launched"}'
    )
    mock_get_client.return_value = mock_client

    result = is_dated_action(
        title="GAO Launches New Investigation into VA Contracts",
        content="GAO announced today it is launching an investigation...",
    )

    assert result["is_dated_action"] is True


@patch("src.oversight.pipeline.classifier._get_client")
def test_is_dated_action_false_historical(mock_get_client, mock_anthropic_response):
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_anthropic_response(
        '{"is_dated_action": false, "explanation": "Historical reference to 2019 event"}'
    )
    mock_get_client.return_value = mock_client

    result = is_dated_action(
        title="Review of Past Oversight Actions",
        content="The 2019 criminal referral led to reforms...",
    )

    assert result["is_dated_action"] is False


@patch("src.oversight.pipeline.classifier._get_client")
def test_classify_event_full(mock_get_client, mock_anthropic_response):
    mock_client = MagicMock()
    # Return VA relevant and dated action
    mock_client.messages.create.side_effect = [
        mock_anthropic_response('{"is_va_relevant": true, "explanation": "VA healthcare report"}'),
        mock_anthropic_response('{"is_dated_action": true, "explanation": "Current action"}'),
    ]
    mock_get_client.return_value = mock_client

    result = classify_event(
        title="GAO Report on VA Healthcare",
        content="New GAO report released today...",
    )

    assert result.is_va_relevant is True
    assert result.is_dated_action is True
    assert result.should_process is True


def test_is_va_relevant_missing_key_fails_open(monkeypatch):
    def raise_missing_key(*_args, **_kwargs):
        raise RuntimeError("No ANTHROPIC_API_KEY found")

    monkeypatch.setattr(
        "src.oversight.pipeline.classifier.get_env_or_keychain",
        raise_missing_key,
    )

    result = is_va_relevant(
        title="GAO Report on VA Healthcare",
        content="This report examines wait times at VA medical centers...",
    )

    assert result["is_va_relevant"] is True
    assert "assuming relevant" in result["explanation"].lower()


def test_is_dated_action_missing_key_fails_open(monkeypatch):
    def raise_missing_key(*_args, **_kwargs):
        raise RuntimeError("No ANTHROPIC_API_KEY found")

    monkeypatch.setattr(
        "src.oversight.pipeline.classifier.get_env_or_keychain",
        raise_missing_key,
    )

    result = is_dated_action(
        title="GAO Launches New Investigation into VA Contracts",
        content="GAO announced today it is launching an investigation...",
    )

    assert result["is_dated_action"] is True
    assert "assuming dated" in result["explanation"].lower()
