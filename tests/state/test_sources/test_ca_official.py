"""Tests for California official sources."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.state.sources.ca_official import CAOfficialSource


@pytest.fixture
def calvet_html():
    fixture_path = Path(__file__).parent.parent / "fixtures" / "calvet_news.html"
    return fixture_path.read_text()


def test_ca_source_attributes():
    source = CAOfficialSource()
    assert source.source_id == "ca_calvet_news"
    assert source.state == "CA"


def test_ca_source_parse_calvet_news(calvet_html):
    source = CAOfficialSource()

    with patch("src.state.sources.ca_official.CALVET_DISABLED", False):
        with patch("src.state.sources.ca_official.httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.text = calvet_html
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            signals = source.fetch()

    assert len(signals) >= 2
    assert any("PACT" in s.title for s in signals)


def test_ca_source_extracts_dates(calvet_html):
    source = CAOfficialSource()

    with patch("src.state.sources.ca_official.CALVET_DISABLED", False):
        with patch("src.state.sources.ca_official.httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.text = calvet_html
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            signals = source.fetch()

    pact_signal = next((s for s in signals if "PACT" in s.title), None)
    assert pact_signal is not None
    assert pact_signal.pub_date == "2026-01-19"


def test_ca_source_handles_error():
    source = CAOfficialSource()

    with patch("src.state.sources.ca_official.CALVET_DISABLED", False):
        with patch("src.state.sources.ca_official.httpx.get") as mock_get:
            mock_get.side_effect = Exception("Connection error")

            signals = source.fetch()

    assert signals == []


def test_ca_source_disabled_returns_empty():
    """When CALVET_DISABLED is True, fetch returns empty list."""
    source = CAOfficialSource()

    # Don't patch CALVET_DISABLED - it's True by default
    signals = source.fetch()

    assert signals == []
