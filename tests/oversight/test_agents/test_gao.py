"""Tests for GAO agent."""

import pytest
from unittest.mock import patch, MagicMock

from src.oversight.agents.gao import GAOAgent


SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>GAO Reports</title>
    <item>
      <title>VA Health Care: Test Report</title>
      <link>https://www.gao.gov/products/gao-26-123456</link>
      <pubDate>Mon, 20 Jan 2026 10:00:00 EST</pubDate>
      <description>This report examines VA health care...</description>
    </item>
    <item>
      <title>DOD Equipment: Non-VA Report</title>
      <link>https://www.gao.gov/products/gao-26-999999</link>
      <pubDate>Mon, 20 Jan 2026 09:00:00 EST</pubDate>
      <description>This report examines DOD equipment...</description>
    </item>
  </channel>
</rss>
"""


@pytest.fixture
def gao_agent():
    return GAOAgent()


def test_gao_agent_source_type(gao_agent):
    assert gao_agent.source_type == "gao"


@patch("src.oversight.agents.gao.feedparser.parse")
def test_gao_fetch_new(mock_parse, gao_agent):
    # Mock feedparser response
    mock_parse.return_value = MagicMock(
        entries=[
            MagicMock(
                title="VA Health Care: Test Report",
                link="https://www.gao.gov/products/gao-26-123456",
                published="Mon, 20 Jan 2026 10:00:00 EST",
                summary="This report examines VA health care...",
            ),
        ]
    )

    events = gao_agent.fetch_new(since=None)

    assert len(events) == 1
    assert "VA Health Care" in events[0].title
    assert "gao-26-123456" in events[0].url


def test_gao_extract_timestamps(gao_agent):
    from src.oversight.agents.base import RawEvent

    raw = RawEvent(
        url="https://www.gao.gov/products/gao-26-123456",
        title="VA Health Care Report",
        raw_html="",
        fetched_at="2026-01-20T15:00:00Z",
        metadata={"published": "Mon, 20 Jan 2026 10:00:00 EST"},
    )

    result = gao_agent.extract_timestamps(raw)

    assert result.pub_timestamp is not None
    assert "2026-01-20" in result.pub_timestamp
    assert result.pub_precision == "datetime"
    assert result.pub_source == "extracted"


def test_gao_extract_canonical_refs(gao_agent):
    from src.oversight.agents.base import RawEvent

    raw = RawEvent(
        url="https://www.gao.gov/products/gao-26-123456",
        title="VA Health Care Report",
        raw_html="",
        fetched_at="2026-01-20T15:00:00Z",
    )

    refs = gao_agent.extract_canonical_refs(raw)

    assert refs.get("gao_report") == "GAO-26-123456"
