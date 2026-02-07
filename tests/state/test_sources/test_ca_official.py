"""Tests for California official sources."""

from pathlib import Path

import pytest

from src.state.sources.ca_official import CAOfficialSource


@pytest.fixture
def calvet_html():
    fixture_path = Path(__file__).parent.parent / "fixtures" / "calvet_news.html"
    return fixture_path.read_text()


def test_ca_source_attributes():
    source = CAOfficialSource()
    assert source.source_id == "ca_calvet_news"
    assert source.state == "CA"


def test_ca_source_disabled_returns_empty():
    """When CALVET_DISABLED is True, fetch returns empty list."""
    source = CAOfficialSource()

    # Don't patch CALVET_DISABLED - it's True by default
    signals = source.fetch()

    assert signals == []


def test_ca_source_parse_calvet_news(calvet_html):
    """Test HTML parsing logic when source is enabled."""
    source = CAOfficialSource()

    # Test the parsing method directly
    signals = source._parse_calvet_news(calvet_html)

    assert len(signals) >= 2
    assert any("PACT" in s.title for s in signals)


def test_ca_source_extracts_dates(calvet_html):
    """Test date extraction from HTML."""
    source = CAOfficialSource()

    signals = source._parse_calvet_news(calvet_html)

    pact_signal = next((s for s in signals if "PACT" in s.title), None)
    assert pact_signal is not None
    assert pact_signal.pub_date == "2026-01-19"


def test_ca_source_parse_date_text():
    """Test date text parsing formats."""
    source = CAOfficialSource()

    assert source._parse_date_text("01/19/2026") == "2026-01-19"
    assert source._parse_date_text("January 19, 2026") == "2026-01-19"
    assert source._parse_date_text("Jan 19, 2026") == "2026-01-19"
    assert source._parse_date_text("2026-01-19") == "2026-01-19"
    assert source._parse_date_text("invalid") is None
