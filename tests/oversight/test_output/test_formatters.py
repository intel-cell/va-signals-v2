"""Tests for output formatters."""

import pytest

from src.oversight.output.formatters import (
    format_escalation_alert,
    format_weekly_digest,
    group_events_by_theme,
)


@pytest.fixture
def sample_escalation_event():
    return {
        "event_id": "esc-123",
        "event_type": "report_release",
        "theme": "fraud",
        "primary_source_type": "gao",
        "primary_url": "https://gao.gov/products/gao-26-123",
        "title": "GAO Criminal Referral: VA Contract Fraud",
        "summary": "GAO has referred VA contracting officials to DOJ...",
        "pub_timestamp": "2026-01-20T10:00:00Z",
        "is_escalation": 1,
        "escalation_signals": ["criminal referral"],
    }


@pytest.fixture
def sample_deviation_event():
    return {
        "event_id": "dev-456",
        "event_type": "report_release",
        "theme": "technology",
        "primary_source_type": "gao",
        "primary_url": "https://gao.gov/products/gao-26-456",
        "title": "First GAO Report on AI in VA Healthcare",
        "summary": "This report examines the deployment of AI...",
        "pub_timestamp": "2026-01-19T14:00:00Z",
        "is_deviation": 1,
        "deviation_reason": "First report on AI topic",
    }


def test_format_escalation_alert(sample_escalation_event):
    subject, html, text = format_escalation_alert(sample_escalation_event)

    assert subject is not None
    assert "criminal referral" in subject.lower()
    assert "GAO Criminal Referral" in html
    assert "GAO Criminal Referral" in text
    assert "gao.gov" in html
    assert "gao.gov" in text


def test_format_escalation_alert_with_severity(sample_escalation_event):
    sample_escalation_event["escalation_severity"] = "critical"
    subject, html, text = format_escalation_alert(sample_escalation_event)

    # Critical severity should be indicated
    assert "CRITICAL" in subject


def test_group_events_by_theme():
    events = [
        {"event_id": "1", "theme": "healthcare", "title": "Health Report 1"},
        {"event_id": "2", "theme": "healthcare", "title": "Health Report 2"},
        {"event_id": "3", "theme": "benefits", "title": "Benefits Report"},
        {"event_id": "4", "theme": None, "title": "General Report"},
    ]

    grouped = group_events_by_theme(events)

    assert "healthcare" in grouped
    assert len(grouped["healthcare"]) == 2
    assert "benefits" in grouped
    assert len(grouped["benefits"]) == 1
    assert "other" in grouped or None in grouped


def test_format_weekly_digest():
    events = [
        {
            "event_id": "1",
            "theme": "healthcare",
            "title": "Health Report",
            "primary_source_type": "gao",
            "primary_url": "https://example.com/1",
            "pub_timestamp": "2026-01-20T10:00:00Z",
            "is_escalation": 1,
            "is_deviation": 0,
        },
        {
            "event_id": "2",
            "theme": "benefits",
            "title": "Benefits Report",
            "primary_source_type": "oig",
            "primary_url": "https://example.com/2",
            "pub_timestamp": "2026-01-19T10:00:00Z",
            "is_escalation": 0,
            "is_deviation": 1,
        },
    ]

    digest = format_weekly_digest(
        events=events,
        period_start="2026-01-13",
        period_end="2026-01-20",
    )

    assert digest is not None
    assert "2026-01-13" in digest
    assert len(digest) > 100  # Should have substantial content


def test_format_weekly_digest_empty():
    digest = format_weekly_digest(
        events=[],
        period_start="2026-01-13",
        period_end="2026-01-20",
    )

    assert "no significant" in digest.lower() or "quiet" in digest.lower()
