"""Tests for Florida official sources."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.state.sources.fl_official import FLOfficialSource


@pytest.fixture
def fl_dva_html():
    fixture_path = Path(__file__).parent.parent / "fixtures" / "fl_dva_news.html"
    return fixture_path.read_text()


def test_fl_source_attributes():
    source = FLOfficialSource()
    assert source.source_id == "fl_dva_news"
    assert source.state == "FL"


def test_fl_source_parse_dva_news(fl_dva_html):
    source = FLOfficialSource()

    with patch("src.state.sources.fl_official.httpx.get") as mock_get:
        mock_response = MagicMock()
        mock_response.text = fl_dva_html
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        signals = source.fetch()

    assert len(signals) >= 2
    assert any("PACT" in s.title for s in signals)


def test_fl_source_extracts_dates(fl_dva_html):
    source = FLOfficialSource()

    with patch("src.state.sources.fl_official.httpx.get") as mock_get:
        mock_response = MagicMock()
        mock_response.text = fl_dva_html
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        signals = source.fetch()

    pact_signal = next((s for s in signals if "PACT" in s.title), None)
    assert pact_signal is not None
    assert pact_signal.pub_date == "2026-01-21"


def test_fl_source_handles_error():
    source = FLOfficialSource()

    with patch("src.state.sources.fl_official.httpx.get") as mock_get:
        mock_get.side_effect = Exception("Connection error")

        signals = source.fetch()

    assert signals == []
