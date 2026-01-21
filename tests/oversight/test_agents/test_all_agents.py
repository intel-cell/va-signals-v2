"""Tests for all oversight agents."""

import pytest
from unittest.mock import patch, MagicMock

from src.oversight.agents import (
    GAOAgent,
    OIGAgent,
    CRSAgent,
    CongressionalRecordAgent,
    CommitteePressAgent,
    NewsWireAgent,
    InvestigativeAgent,
    TradePressAgent,
    CAFCAgent,
)
from src.oversight.agents.base import RawEvent


def test_gao_agent_source_type():
    agent = GAOAgent()
    assert agent.source_type == "gao"


def test_oig_agent_source_type():
    agent = OIGAgent()
    assert agent.source_type == "oig"


def test_crs_agent_source_type():
    agent = CRSAgent()
    assert agent.source_type == "crs"


def test_congressional_record_agent_source_type():
    agent = CongressionalRecordAgent()
    assert agent.source_type == "congressional_record"


def test_committee_press_agent_source_type():
    agent = CommitteePressAgent()
    assert agent.source_type == "committee_press"


def test_news_wire_agent_source_type():
    agent = NewsWireAgent()
    assert agent.source_type == "news_wire"


def test_investigative_agent_source_type():
    agent = InvestigativeAgent()
    assert agent.source_type == "investigative"


def test_trade_press_agent_source_type():
    agent = TradePressAgent()
    assert agent.source_type == "trade_press"


def test_cafc_agent_source_type():
    agent = CAFCAgent()
    assert agent.source_type == "cafc"


def test_oig_extract_canonical_refs():
    agent = OIGAgent()
    raw = RawEvent(
        url="https://www.va.gov/oig/reports/22-01234-567",
        title="VA OIG Report 22-01234-567",
        raw_html="",
        fetched_at="2026-01-20T12:00:00Z",
    )

    refs = agent.extract_canonical_refs(raw)
    assert "oig_report" in refs


def test_crs_extract_canonical_refs():
    agent = CRSAgent()
    raw = RawEvent(
        url="https://crsreports.congress.gov/R45678",
        title="CRS Report R45678",
        raw_html="",
        fetched_at="2026-01-20T12:00:00Z",
    )

    refs = agent.extract_canonical_refs(raw)
    assert refs.get("crs_report") == "R45678"


def test_cafc_extract_canonical_refs():
    agent = CAFCAgent()
    raw = RawEvent(
        url="https://cafc.uscourts.gov/opinions/2024-1234",
        title="Smith v. McDonough, No. 2024-1234 (precedential)",
        raw_html="",
        fetched_at="2026-01-20T12:00:00Z",
    )

    refs = agent.extract_canonical_refs(raw)
    assert refs.get("cafc_case") == "2024-1234"


def test_investigative_va_filter():
    agent = InvestigativeAgent()

    assert agent._is_va_related("VA Hospital Investigation", "The VA hospital...")
    assert agent._is_va_related("Veterans Affairs Scandal", "The department...")
    assert not agent._is_va_related("DOD Budget Review", "The defense department...")


def test_trade_press_va_filter():
    agent = TradePressAgent()

    assert agent._is_va_related("VA Announces New IT System", "Veterans Affairs...")
    assert not agent._is_va_related("HHS Budget Update", "The department of health...")


@patch("src.oversight.agents.oig.feedparser.parse")
def test_oig_fetch_new(mock_parse):
    mock_parse.return_value = MagicMock(
        entries=[
            MagicMock(
                title="OIG Report on VA Healthcare",
                link="https://va.gov/oig/test",
                published="Mon, 20 Jan 2026 10:00:00 EST",
                published_parsed=(2026, 1, 20, 10, 0, 0, 0, 0, 0),
                summary="Test summary",
            ),
        ]
    )

    agent = OIGAgent()
    events = agent.fetch_new(since=None)

    assert len(events) == 1
    assert "OIG Report" in events[0].title
