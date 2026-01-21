"""Tests for OM events adapter."""

import pytest
from src.signals.adapters.om_events import OMEventsAdapter
from src.signals.envelope import Envelope


def test_adapt_om_event_to_envelope():
    adapter = OMEventsAdapter()
    event = {
        "event_id": "gao-26-12345",
        "event_type": "report",
        "theme": "veterans_benefits",
        "primary_source_type": "gao",
        "primary_url": "https://gao.gov/reports/...",
        "pub_timestamp": "2026-01-15T12:00:00Z",
        "pub_precision": "day",
        "pub_source": "gao",
        "title": "GAO Report on VA Disability Claims",
        "summary": "Review of VA disability claims processing",
        "fetched_at": "2026-01-15T14:00:00Z",
    }

    envelope = adapter.adapt(event)

    assert isinstance(envelope, Envelope)
    assert envelope.event_id == "om-gao-26-12345"
    assert envelope.authority_id == "gao-26-12345"
    assert envelope.authority_source == "govinfo"
    assert envelope.authority_type == "report"
    assert "disability_benefits" in envelope.topics


def test_adapt_om_event_maps_source_types():
    adapter = OMEventsAdapter()

    # GAO -> govinfo
    event = _make_om_event(primary_source_type="gao")
    env = adapter.adapt(event)
    assert env.authority_source == "govinfo"

    # CRS -> congress_gov
    event = _make_om_event(primary_source_type="crs")
    env = adapter.adapt(event)
    assert env.authority_source == "congress_gov"

    # OIG -> govinfo
    event = _make_om_event(primary_source_type="oig")
    env = adapter.adapt(event)
    assert env.authority_source == "govinfo"

    # news_wire -> news
    event = _make_om_event(primary_source_type="news_wire")
    env = adapter.adapt(event)
    assert env.authority_source == "news"

    # investigative -> news
    event = _make_om_event(primary_source_type="investigative")
    env = adapter.adapt(event)
    assert env.authority_source == "news"


def test_adapt_om_event_maps_event_types():
    adapter = OMEventsAdapter()

    # report -> report
    event = _make_om_event(event_type="report")
    env = adapter.adapt(event)
    assert env.authority_type == "report"

    # hearing -> hearing_notice
    event = _make_om_event(event_type="hearing")
    env = adapter.adapt(event)
    assert env.authority_type == "hearing_notice"

    # press_release -> press_release
    event = _make_om_event(event_type="press_release")
    env = adapter.adapt(event)
    assert env.authority_type == "press_release"


def test_adapt_om_event_preserves_escalation_metadata():
    adapter = OMEventsAdapter()
    event = _make_om_event(
        is_escalation=1,
        escalation_signals="GAO_REPORT",
    )
    env = adapter.adapt(event)
    assert env.metadata["is_escalation"] == 1
    assert env.metadata["escalation_signals"] == "GAO_REPORT"


def test_adapt_om_event_preserves_deviation_metadata():
    adapter = OMEventsAdapter()
    event = _make_om_event(
        is_deviation=1,
        deviation_reason="Unexpected policy shift",
    )
    env = adapter.adapt(event)
    assert env.metadata["is_deviation"] == 1
    assert env.metadata["deviation_reason"] == "Unexpected policy shift"


def test_adapt_om_event_computes_version():
    adapter = OMEventsAdapter()
    event = _make_om_event()

    # First version
    env1 = adapter.adapt(event, version=1)
    assert env1.version == 1

    # Updated version
    env2 = adapter.adapt(event, version=2)
    assert env2.version == 2


def test_adapt_om_event_builds_body_text():
    adapter = OMEventsAdapter()
    event = _make_om_event(
        title="Test Report Title",
        summary="Detailed summary of findings"
    )
    env = adapter.adapt(event)

    assert "Test Report Title" in env.body_text
    assert "Detailed summary of findings" in env.body_text


def test_adapt_om_event_uses_raw_content_fallback():
    adapter = OMEventsAdapter()
    event = _make_om_event(
        title="",
        summary="",
        raw_content="Raw content fallback text" + "x" * 2000
    )
    env = adapter.adapt(event)

    # Should use raw_content truncated to 1000 chars
    assert "Raw content fallback text" in env.body_text
    assert len(env.body_text) <= 1000


def test_adapt_om_event_sets_published_at_source():
    adapter = OMEventsAdapter()

    # Day precision -> authority
    event = _make_om_event(pub_precision="day")
    env = adapter.adapt(event)
    assert env.published_at_source == "authority"

    # Other precision -> derived
    event = _make_om_event(pub_precision="month")
    env = adapter.adapt(event)
    assert env.published_at_source == "derived"


def test_adapt_om_event_extracts_topics():
    adapter = OMEventsAdapter()

    # Disability benefits topic
    event = _make_om_event(title="Report on Veteran Benefits")
    env = adapter.adapt(event)
    assert "disability_benefits" in env.topics

    # Exam quality topic
    event = _make_om_event(summary="Review of contractor exam quality")
    env = adapter.adapt(event)
    assert "exam_quality" in env.topics


def test_adapt_om_event_sets_event_start_at():
    adapter = OMEventsAdapter()
    event = _make_om_event(event_timestamp="2026-01-20T14:00:00Z")
    env = adapter.adapt(event)

    assert env.event_start_at == "2026-01-20T14:00:00Z"


def _make_om_event(**overrides):
    base = {
        "event_id": "test-001",
        "event_type": "report",
        "primary_source_type": "gao",
        "primary_url": "https://example.com",
        "title": "Test Event",
        "fetched_at": "2026-01-15T12:00:00Z",
    }
    base.update(overrides)
    return base
