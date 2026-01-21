"""Tests for Texas official sources."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.state.sources.tx_official import TXOfficialSource
from src.state.common import RawSignal


@pytest.fixture
def tvc_html():
    fixture_path = Path(__file__).parent.parent / "fixtures" / "tvc_news.html"
    return fixture_path.read_text()


def test_tx_source_attributes():
    source = TXOfficialSource()
    assert source.source_id == "tx_tvc_news"
    assert source.state == "TX"


def test_tx_source_parse_tvc_news(tvc_html):
    source = TXOfficialSource()

    with patch("src.state.sources.tx_official.httpx.get") as mock_get:
        mock_response = MagicMock()
        mock_response.text = tvc_html
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        signals = source.fetch()

    assert len(signals) >= 2
    assert any("PACT Act" in s.title for s in signals)


def test_tx_source_extracts_dates(tvc_html):
    source = TXOfficialSource()

    with patch("src.state.sources.tx_official.httpx.get") as mock_get:
        mock_response = MagicMock()
        mock_response.text = tvc_html
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        signals = source.fetch()

    pact_signal = next((s for s in signals if "PACT" in s.title), None)
    assert pact_signal is not None
    assert pact_signal.pub_date == "2026-01-20"


def test_tx_source_handles_error():
    source = TXOfficialSource()

    with patch("src.state.sources.tx_official.httpx.get") as mock_get:
        mock_get.side_effect = Exception("Connection error")

        signals = source.fetch()

    assert signals == []
