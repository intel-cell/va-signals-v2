"""Tests for NewsAPI news source."""

from unittest.mock import MagicMock, patch

from src.state.sources.newsapi import SEARCH_QUERIES, NewsAPISource


def test_newsapi_source_attributes():
    source = NewsAPISource(state="TX")
    assert source.source_id == "newsapi_tx"
    assert source.state == "TX"


def test_newsapi_search_queries_defined():
    assert "TX" in SEARCH_QUERIES
    assert "CA" in SEARCH_QUERIES
    assert "FL" in SEARCH_QUERIES
    assert len(SEARCH_QUERIES["TX"]) >= 2


@patch("src.state.sources.newsapi._get_newsapi_key")
@patch("src.state.sources.newsapi.httpx.get")
def test_newsapi_fetch_parses_response(mock_get, mock_key):
    mock_key.return_value = "test-api-key"

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "status": "ok",
        "articles": [
            {
                "title": "Texas veterans PACT Act expansion",
                "url": "https://example.com/news/1",
                "description": "Texas announces PACT Act screening expansion...",
                "publishedAt": "2026-01-20T10:00:00Z",
            },
            {
                "title": "VA community care in Houston",
                "url": "https://example.com/news/2",
                "description": "New community care providers...",
                "publishedAt": "2026-01-19T15:00:00Z",
            },
        ],
    }
    mock_response.raise_for_status = MagicMock()
    mock_get.return_value = mock_response

    source = NewsAPISource(state="TX")
    signals = source.fetch()

    assert len(signals) >= 2
    assert any("PACT" in s.title for s in signals)
    assert all(s.state == "TX" for s in signals)


@patch("src.state.sources.newsapi._get_newsapi_key")
@patch("src.state.sources.newsapi.httpx.get")
def test_newsapi_handles_error(mock_get, mock_key):
    mock_key.return_value = "test-api-key"
    mock_get.side_effect = Exception("API error")

    source = NewsAPISource(state="TX")
    signals = source.fetch()

    assert signals == []


@patch("src.state.sources.newsapi._get_newsapi_key")
@patch("src.state.sources.newsapi.httpx.get")
def test_newsapi_deduplicates_by_url(mock_get, mock_key):
    mock_key.return_value = "test-api-key"

    # Two queries return overlapping articles
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "status": "ok",
        "articles": [
            {
                "title": "Duplicate article",
                "url": "https://example.com/same-url",
                "description": "Same article from different query",
                "publishedAt": "2026-01-20T10:00:00Z",
            },
        ],
    }
    mock_response.raise_for_status = MagicMock()
    mock_get.return_value = mock_response

    source = NewsAPISource(state="TX")
    signals = source.fetch()

    # Should have deduplicated by URL
    urls = [s.url for s in signals]
    assert len(urls) == len(set(urls))
