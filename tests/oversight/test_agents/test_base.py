"""Tests for base agent class."""

from src.oversight.agents.base import (
    OversightAgent,
    RawEvent,
    TimestampResult,
)


class MockAgent(OversightAgent):
    """Concrete implementation for testing."""

    source_type = "mock"

    def fetch_new(self, since):
        return [
            RawEvent(
                url="https://example.com/1",
                title="Test Event",
                raw_html="<p>Content</p>",
                fetched_at="2026-01-20T12:00:00Z",
            )
        ]

    def backfill(self, start, end):
        return []

    def extract_timestamps(self, raw):
        return TimestampResult(
            pub_timestamp="2026-01-20T10:00:00Z",
            pub_precision="datetime",
            pub_source="extracted",
        )


def test_raw_event_creation():
    event = RawEvent(
        url="https://example.com",
        title="Test",
        raw_html="<p>Test</p>",
        fetched_at="2026-01-20T12:00:00Z",
    )
    assert event.url == "https://example.com"
    assert event.title == "Test"


def test_timestamp_result_defaults():
    result = TimestampResult(
        pub_timestamp="2026-01-20",
        pub_precision="date",
        pub_source="extracted",
    )
    assert result.event_timestamp is None
    assert result.event_precision is None


def test_agent_source_type():
    agent = MockAgent()
    assert agent.source_type == "mock"


def test_agent_fetch_new():
    agent = MockAgent()
    events = agent.fetch_new(since=None)
    assert len(events) == 1
    assert events[0].title == "Test Event"


def test_agent_extract_timestamps():
    agent = MockAgent()
    raw = RawEvent(
        url="https://example.com",
        title="Test",
        raw_html="",
        fetched_at="2026-01-20T12:00:00Z",
    )
    result = agent.extract_timestamps(raw)
    assert result.pub_precision == "datetime"
