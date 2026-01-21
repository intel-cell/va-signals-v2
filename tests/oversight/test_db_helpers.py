"""Tests for oversight DB helpers."""

import pytest
from datetime import datetime, timezone

from src.oversight.db_helpers import (
    insert_om_event,
    get_om_event,
    update_om_event_surfaced,
    insert_om_rejected,
    get_om_events_for_digest,
    insert_om_escalation_signal,
    get_active_escalation_signals,
    seed_default_escalation_signals,
)


def test_insert_and_get_om_event():
    event = {
        "event_id": "test-gao-123",
        "event_type": "report_release",
        "theme": "healthcare",
        "primary_source_type": "gao",
        "primary_url": "https://gao.gov/test",
        "pub_timestamp": "2026-01-20T10:00:00Z",
        "pub_precision": "datetime",
        "pub_source": "extracted",
        "title": "Test GAO Report",
        "fetched_at": "2026-01-20T12:00:00Z",
    }

    insert_om_event(event)
    result = get_om_event("test-gao-123")

    assert result is not None
    assert result["event_id"] == "test-gao-123"
    assert result["theme"] == "healthcare"
    assert result["surfaced"] == 0


def test_update_om_event_surfaced():
    event = {
        "event_id": "test-surf-456",
        "event_type": "hearing",
        "primary_source_type": "committee_press",
        "primary_url": "https://example.com",
        "pub_timestamp": "2026-01-20T10:00:00Z",
        "pub_precision": "datetime",
        "pub_source": "extracted",
        "title": "Test Hearing",
        "fetched_at": "2026-01-20T12:00:00Z",
    }
    insert_om_event(event)

    update_om_event_surfaced("test-surf-456", "immediate_alert")

    result = get_om_event("test-surf-456")
    assert result["surfaced"] == 1
    assert result["surfaced_via"] == "immediate_alert"
    assert result["surfaced_at"] is not None


def test_insert_om_rejected():
    rejected = {
        "source_type": "news_wire",
        "url": "https://example.com/article",
        "title": "How to Apply for VA Benefits",
        "pub_timestamp": "2026-01-20T10:00:00Z",
        "rejection_reason": "not_dated_action",
        "fetched_at": "2026-01-20T12:00:00Z",
    }

    result_id = insert_om_rejected(rejected)
    assert result_id > 0


def test_get_om_events_for_digest():
    # Insert a deviation event
    event = {
        "event_id": "test-digest-789",
        "event_type": "report_release",
        "theme": "housing_loans",
        "primary_source_type": "gao",
        "primary_url": "https://gao.gov/test2",
        "pub_timestamp": "2026-01-20T10:00:00Z",
        "pub_precision": "datetime",
        "pub_source": "extracted",
        "title": "Housing Report",
        "is_deviation": 1,
        "fetched_at": "2026-01-20T12:00:00Z",
    }
    insert_om_event(event)

    events = get_om_events_for_digest(
        start_date="2026-01-19",
        end_date="2026-01-21"
    )

    assert len(events) >= 1
    assert any(e["event_id"] == "test-digest-789" for e in events)


def test_escalation_signals():
    signal = {
        "signal_pattern": "test signal",
        "signal_type": "keyword",
        "severity": "high",
        "description": "Test signal for testing",
    }

    insert_om_escalation_signal(signal)
    signals = get_active_escalation_signals()

    assert any(s["signal_pattern"] == "test signal" for s in signals)


def test_seed_default_escalation_signals():
    seed_default_escalation_signals()
    signals = get_active_escalation_signals()

    # Should have the default signals
    patterns = [s["signal_pattern"] for s in signals]
    assert "criminal referral" in patterns
    assert "subpoena" in patterns
    assert "whistleblower" in patterns
