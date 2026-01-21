"""Tests for RSS news source."""

import pytest
from unittest.mock import patch, MagicMock

from src.state.sources.rss import RSSSource, RSS_FEEDS
from src.state.common import RawSignal


def _make_feed_entry(title, link, summary, published_parsed):
    """Create a mock feed entry that behaves like feedparser entries."""
    entry = MagicMock()
    entry.get = lambda key, default="": {
        "title": title,
        "link": link,
        "summary": summary,
        "published_parsed": published_parsed,
    }.get(key, default)
    entry.published_parsed = published_parsed
    return entry


def test_rss_source_attributes():
    source = RSSSource(state="TX")
    assert source.source_id == "rss_tx"
    assert source.state == "TX"


def test_rss_feeds_defined():
    assert "TX" in RSS_FEEDS
    assert "CA" in RSS_FEEDS
    assert "FL" in RSS_FEEDS
    # Each state should have at least one feed
    assert len(RSS_FEEDS["TX"]) >= 1


@patch("src.state.sources.rss.feedparser.parse")
def test_rss_fetch_parses_feed(mock_parse):
    mock_parse.return_value = MagicMock(
        entries=[
            _make_feed_entry(
                title="Texas veterans receive PACT Act benefits",
                link="https://texastribune.org/2026/01/20/veterans-pact-act/",
                summary="Texas veterans are now eligible...",
                published_parsed=(2026, 1, 20, 10, 0, 0, 0, 0, 0),
            ),
            _make_feed_entry(
                title="State budget includes veteran funding",
                link="https://texastribune.org/2026/01/19/budget-veterans/",
                summary="The state budget allocates...",
                published_parsed=(2026, 1, 19, 15, 0, 0, 0, 0, 0),
            ),
        ]
    )

    source = RSSSource(state="TX")
    signals = source.fetch()

    assert len(signals) >= 2
    assert any("PACT" in s.title for s in signals)
    assert all(s.state == "TX" for s in signals)


@patch("src.state.sources.rss.feedparser.parse")
def test_rss_handles_error(mock_parse):
    mock_parse.side_effect = Exception("Feed parse error")

    source = RSSSource(state="TX")
    signals = source.fetch()

    assert signals == []


@patch("src.state.sources.rss.feedparser.parse")
def test_rss_filters_veteran_relevant(mock_parse):
    """Only veteran-relevant articles should be included."""
    mock_parse.return_value = MagicMock(
        entries=[
            _make_feed_entry(
                title="Local bakery opens new location",
                link="https://example.com/bakery",
                summary="A new bakery in downtown...",
                published_parsed=(2026, 1, 20, 10, 0, 0, 0, 0, 0),
            ),
            _make_feed_entry(
                title="Veterans Day celebration planned",
                link="https://example.com/veterans-day",
                summary="Veterans will be honored...",
                published_parsed=(2026, 1, 19, 15, 0, 0, 0, 0, 0),
            ),
        ]
    )

    source = RSSSource(state="TX")
    signals = source.fetch()

    # Should only have the veteran-related article
    assert len(signals) == 1
    assert "Veterans" in signals[0].title
