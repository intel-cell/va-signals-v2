"""Tests for oversight CLI runner."""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

from src.oversight.runner import (
    run_agent,
    run_all_agents,
    run_backfill,
    generate_digest,
    OversightRunResult,
)


def test_run_result_creation():
    result = OversightRunResult(
        agent="gao",
        status="SUCCESS",
        events_fetched=5,
        events_processed=4,
        escalations=1,
        deviations=1,
        errors=[],
    )
    assert result.agent == "gao"
    assert result.status == "SUCCESS"


def test_run_result_with_errors():
    result = OversightRunResult(
        agent="oig",
        status="ERROR",
        events_fetched=0,
        events_processed=0,
        escalations=0,
        deviations=0,
        errors=["Connection timeout"],
    )
    assert result.status == "ERROR"
    assert len(result.errors) == 1


@patch("src.oversight.runner.AGENT_REGISTRY")
def test_run_agent_gao(mock_registry):
    mock_agent = MagicMock()
    mock_agent.source_type = "gao"
    mock_agent.fetch_new.return_value = []

    mock_agent_class = MagicMock(return_value=mock_agent)
    mock_registry.__contains__ = lambda self, x: x == "gao"
    mock_registry.__getitem__ = lambda self, x: mock_agent_class

    result = run_agent("gao")

    assert result.agent == "gao"
    assert result.status == "NO_DATA"


@patch("src.oversight.runner.AGENT_REGISTRY")
def test_run_agent_with_events(mock_registry):
    from src.oversight.agents.base import RawEvent

    mock_agent = MagicMock()
    mock_agent.source_type = "gao"
    mock_agent.fetch_new.return_value = [
        RawEvent(
            url="https://gao.gov/test",
            title="Test Report",
            raw_html="<p>Content</p>",
            fetched_at="2026-01-20T12:00:00Z",
            metadata={"published": "Mon, 20 Jan 2026 10:00:00 EST"},
        )
    ]
    mock_agent.extract_timestamps.return_value = MagicMock(
        pub_timestamp="2026-01-20T10:00:00Z",
        pub_precision="datetime",
        pub_source="extracted",
    )
    mock_agent.extract_canonical_refs.return_value = {"gao_report": "GAO-26-123"}

    mock_agent_class = MagicMock(return_value=mock_agent)
    mock_registry.__contains__ = lambda self, x: x == "gao"
    mock_registry.__getitem__ = lambda self, x: mock_agent_class

    result = run_agent("gao")

    assert result.events_fetched == 1


def test_run_agent_invalid():
    result = run_agent("invalid_agent")

    assert result.status == "ERROR"
    assert "Unknown agent" in result.errors[0]


@patch("src.oversight.runner.run_agent")
def test_run_all_agents(mock_run_agent):
    mock_run_agent.return_value = OversightRunResult(
        agent="gao",
        status="SUCCESS",
        events_fetched=2,
        events_processed=2,
        escalations=0,
        deviations=0,
        errors=[],
    )

    results = run_all_agents()

    assert len(results) > 0
    mock_run_agent.assert_called()


@patch("src.oversight.runner.get_om_events_for_digest")
def test_generate_digest(mock_get_events):
    mock_get_events.return_value = [
        {
            "event_id": "test-1",
            "title": "Test Event",
            "theme": "healthcare",
            "primary_url": "https://example.com",
            "pub_timestamp": "2026-01-20T10:00:00Z",
            "is_escalation": 1,
            "is_deviation": 0,
        }
    ]

    digest = generate_digest(
        start_date="2026-01-13",
        end_date="2026-01-20",
    )

    assert digest is not None
    assert "Test Event" in digest or len(digest) > 50
