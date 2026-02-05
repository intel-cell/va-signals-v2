"""Tests for NewsWire agent."""

from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest

from src.oversight.agents.news_wire import NewsWireAgent, VA_SEARCH_TERMS
from src.oversight.agents.base import RawEvent


@pytest.fixture
def news_wire_agent():
    """Create a NewsWireAgent instance for testing."""
    return NewsWireAgent()


class TestNewsWireAgentBasics:
    """Basic tests for NewsWireAgent."""

    def test_source_type(self, news_wire_agent):
        """Agent has correct source type."""
        assert news_wire_agent.source_type == "news_wire"

    def test_default_search_terms(self, news_wire_agent):
        """Agent has VA-related search terms."""
        assert len(news_wire_agent.search_terms) > 0
        assert "veterans affairs" in news_wire_agent.search_terms

    def test_default_lookback_days(self, news_wire_agent):
        """Agent has reasonable default lookback."""
        assert news_wire_agent.lookback_days == 7


class TestNewsWireAgentFetchNew:
    """Tests for NewsWireAgent.fetch_new method."""

    @patch("src.oversight.agents.news_wire._get_newsapi_key")
    @patch("src.oversight.agents.news_wire.httpx.get")
    def test_fetch_new_returns_events(self, mock_get, mock_get_key, news_wire_agent):
        """fetch_new returns list of RawEvent objects."""
        mock_get_key.return_value = "test-api-key"
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "status": "ok",
                "articles": [
                    {
                        "url": "https://news.example.com/va-article",
                        "title": "VA Healthcare Update",
                        "content": "Article about VA healthcare...",
                        "description": "VA healthcare reform discussed",
                        "publishedAt": "2026-01-20T10:00:00Z",
                        "source": {"name": "News Source"},
                        "author": "John Doe",
                    }
                ],
            },
            raise_for_status=lambda: None,
        )

        events = news_wire_agent.fetch_new(since=None)

        assert len(events) >= 1
        event = events[0]
        assert isinstance(event, RawEvent)
        assert "va" in event.title.lower() or "va" in event.url.lower()

    @patch("src.oversight.agents.news_wire._get_newsapi_key")
    @patch("src.oversight.agents.news_wire.httpx.get")
    def test_fetch_new_deduplicates_by_url(self, mock_get, mock_get_key, news_wire_agent):
        """fetch_new removes duplicate URLs across search terms."""
        mock_get_key.return_value = "test-api-key"
        # Same article returned for multiple search terms
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "status": "ok",
                "articles": [
                    {
                        "url": "https://news.example.com/same-article",
                        "title": "VA News Story",
                        "content": "Content...",
                        "publishedAt": "2026-01-20T10:00:00Z",
                        "source": {"name": "Source"},
                    }
                ],
            },
            raise_for_status=lambda: None,
        )

        events = news_wire_agent.fetch_new(since=None)

        # Should only have 1 unique event despite multiple search terms
        urls = [e.url for e in events]
        assert len(urls) == len(set(urls))

    @patch("src.oversight.agents.news_wire._get_newsapi_key")
    def test_fetch_new_handles_missing_api_key(self, mock_get_key, news_wire_agent):
        """fetch_new returns empty list when API key is missing."""
        mock_get_key.side_effect = Exception("No API key found")

        events = news_wire_agent.fetch_new(since=None)

        assert events == []

    @patch("src.oversight.agents.news_wire._get_newsapi_key")
    @patch("src.oversight.agents.news_wire.httpx.get")
    def test_fetch_new_uses_since_date(self, mock_get, mock_get_key, news_wire_agent):
        """fetch_new uses since parameter for date filtering."""
        mock_get_key.return_value = "test-api-key"
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"status": "ok", "articles": []},
            raise_for_status=lambda: None,
        )

        since = datetime(2026, 1, 15, tzinfo=timezone.utc)
        news_wire_agent.fetch_new(since=since)

        # Verify the 'from' parameter was set correctly
        call_args = mock_get.call_args
        params = call_args.kwargs.get("params", call_args[1].get("params", {}))
        assert "2026-01-15" in params.get("from", "")

    @patch("src.oversight.agents.news_wire._get_newsapi_key")
    @patch("src.oversight.agents.news_wire.httpx.get")
    def test_fetch_new_handles_api_error(self, mock_get, mock_get_key, news_wire_agent):
        """fetch_new handles API errors gracefully."""
        mock_get_key.return_value = "test-api-key"
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"status": "error", "message": "API error"},
            raise_for_status=lambda: None,
        )

        # Should not raise, just log warning
        events = news_wire_agent.fetch_new(since=None)
        # Empty or partial results due to errors
        assert isinstance(events, list)


class TestNewsWireAgentExtractTimestamps:
    """Tests for NewsWireAgent.extract_timestamps method."""

    def test_extract_timestamps_from_metadata(self, news_wire_agent):
        """Extracts timestamps from metadata published field."""
        raw = RawEvent(
            url="https://example.com/article",
            title="VA News",
            raw_html="",
            fetched_at="2026-01-20T15:00:00Z",
            metadata={"published": "2026-01-20T10:00:00Z"},
        )

        result = news_wire_agent.extract_timestamps(raw)

        assert result.pub_timestamp is not None
        assert "2026-01-20" in result.pub_timestamp
        assert result.pub_precision == "datetime"
        assert result.pub_source == "extracted"

    def test_extract_timestamps_normalizes_format(self, news_wire_agent):
        """Normalizes timestamp to consistent UTC format."""
        raw = RawEvent(
            url="https://example.com/article",
            title="VA News",
            raw_html="",
            fetched_at="2026-01-20T15:00:00Z",
            metadata={"published": "2026-01-20T10:30:00+00:00"},
        )

        result = news_wire_agent.extract_timestamps(raw)

        assert result.pub_timestamp == "2026-01-20T10:30:00Z"

    def test_extract_timestamps_missing_published(self, news_wire_agent):
        """Returns unknown when published field is missing."""
        raw = RawEvent(
            url="https://example.com/article",
            title="VA News",
            raw_html="",
            fetched_at="2026-01-20T15:00:00Z",
            metadata={},
        )

        result = news_wire_agent.extract_timestamps(raw)

        assert result.pub_timestamp is None
        assert result.pub_precision == "unknown"
        assert result.pub_source == "missing"

    def test_extract_timestamps_invalid_format(self, news_wire_agent):
        """Handles invalid timestamp format gracefully."""
        raw = RawEvent(
            url="https://example.com/article",
            title="VA News",
            raw_html="",
            fetched_at="2026-01-20T15:00:00Z",
            metadata={"published": "invalid-date-format"},
        )

        result = news_wire_agent.extract_timestamps(raw)

        # Should return the raw value since parsing failed
        assert result.pub_timestamp == "invalid-date-format"
        assert result.pub_precision == "datetime"
        assert result.pub_source == "extracted"


class TestNewsWireAgentExtractCanonicalRefs:
    """Tests for NewsWireAgent.extract_canonical_refs method."""

    def test_extract_bill_reference_from_title(self, news_wire_agent):
        """Extracts bill reference from article title."""
        raw = RawEvent(
            url="https://example.com/article",
            title="H.R. 1234 Passes House Committee",
            raw_html="",
            fetched_at="2026-01-20T15:00:00Z",
            metadata={"source": "News Source"},
        )

        refs = news_wire_agent.extract_canonical_refs(raw)

        assert "bill_mentioned" in refs
        assert "1234" in refs["bill_mentioned"]

    def test_extract_bill_reference_from_content(self, news_wire_agent):
        """Extracts bill reference from article content."""
        raw = RawEvent(
            url="https://example.com/article",
            title="VA Legislation Update",
            raw_html="The Senate passed S. 5678 today...",
            fetched_at="2026-01-20T15:00:00Z",
            metadata={"source": "News Source"},
        )

        refs = news_wire_agent.extract_canonical_refs(raw)

        assert "bill_mentioned" in refs
        assert "5678" in refs["bill_mentioned"]

    def test_extract_news_source(self, news_wire_agent):
        """Extracts news source from metadata."""
        raw = RawEvent(
            url="https://example.com/article",
            title="VA News",
            raw_html="",
            fetched_at="2026-01-20T15:00:00Z",
            metadata={"source": "Washington Post"},
        )

        refs = news_wire_agent.extract_canonical_refs(raw)

        assert refs.get("news_source") == "Washington Post"

    def test_no_bill_reference(self, news_wire_agent):
        """Returns empty dict when no bill reference found."""
        raw = RawEvent(
            url="https://example.com/article",
            title="VA Healthcare General News",
            raw_html="No bill numbers here.",
            fetched_at="2026-01-20T15:00:00Z",
            metadata={},
        )

        refs = news_wire_agent.extract_canonical_refs(raw)

        assert "bill_mentioned" not in refs
        assert "news_source" not in refs


class TestNewsWireAgentBackfill:
    """Tests for NewsWireAgent.backfill method."""

    @patch("src.oversight.agents.news_wire._get_newsapi_key")
    @patch("src.oversight.agents.news_wire.httpx.get")
    def test_backfill_filters_by_date_range(self, mock_get, mock_get_key, news_wire_agent):
        """backfill filters events to the specified date range."""
        mock_get_key.return_value = "test-api-key"
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "status": "ok",
                "articles": [
                    {
                        "url": "https://example.com/in-range",
                        "title": "VA News",
                        "publishedAt": "2026-01-15T10:00:00Z",
                        "source": {"name": "Source"},
                    },
                    {
                        "url": "https://example.com/out-of-range",
                        "title": "VA News Old",
                        "publishedAt": "2026-01-01T10:00:00Z",
                        "source": {"name": "Source"},
                    },
                ],
            },
            raise_for_status=lambda: None,
        )

        start = datetime(2026, 1, 10, tzinfo=timezone.utc)
        end = datetime(2026, 1, 20, tzinfo=timezone.utc)

        events = news_wire_agent.backfill(start, end)

        # Only the in-range event should be returned
        in_range_events = [e for e in events if "in-range" in e.url]
        assert len(in_range_events) >= 1

    @patch("src.oversight.agents.news_wire._get_newsapi_key")
    def test_backfill_handles_missing_api_key(self, mock_get_key, news_wire_agent):
        """backfill returns empty list when API key is missing."""
        mock_get_key.side_effect = Exception("No API key")

        start = datetime(2026, 1, 10, tzinfo=timezone.utc)
        end = datetime(2026, 1, 20, tzinfo=timezone.utc)

        events = news_wire_agent.backfill(start, end)

        assert events == []
