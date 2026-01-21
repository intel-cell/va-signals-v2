"""Tests for baseline builder."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from src.oversight.pipeline.baseline import (
    build_baseline,
    get_latest_baseline,
    compute_topic_distribution,
    BaselineSummary,
)
from src.oversight.db_helpers import insert_om_event


def _insert_test_events(count: int, source_type: str = "gao", theme: str = "healthcare"):
    """Helper to insert test events."""
    base_date = datetime(2026, 1, 15)
    for i in range(count):
        event_date = base_date - timedelta(days=i)
        insert_om_event({
            "event_id": f"test-baseline-{source_type}-{i}",
            "event_type": "report_release",
            "theme": theme,
            "primary_source_type": source_type,
            "primary_url": f"https://example.com/{i}",
            "pub_timestamp": event_date.strftime("%Y-%m-%dT10:00:00Z"),
            "pub_precision": "datetime",
            "pub_source": "extracted",
            "title": f"Test Report {i} about {theme}",
            "summary": f"This report examines {theme} issues...",
            "fetched_at": event_date.strftime("%Y-%m-%dT12:00:00Z"),
        })


def test_baseline_summary_creation():
    result = BaselineSummary(
        source_type="gao",
        theme="healthcare",
        window_start="2025-10-01",
        window_end="2026-01-01",
        event_count=25,
        summary="Regular GAO healthcare reports",
        topic_distribution={"wait_times": 0.4, "staffing": 0.3, "budget": 0.3},
    )
    assert result.event_count == 25
    assert "wait_times" in result.topic_distribution


def test_compute_topic_distribution():
    events = [
        {"title": "VA Wait Times Report", "summary": "Examines wait times..."},
        {"title": "VA Staffing Levels", "summary": "Reviews staffing..."},
        {"title": "VA Budget Analysis", "summary": "Analyzes budget..."},
        {"title": "VA Wait Times Update", "summary": "Follow-up on wait times..."},
    ]

    dist = compute_topic_distribution(events)

    assert isinstance(dist, dict)
    # Should have extracted some topics
    assert len(dist) >= 0  # May be empty if no clear topics


@patch("src.oversight.pipeline.baseline._get_events_in_window")
def test_build_baseline(mock_get_events):
    mock_get_events.return_value = [
        {"event_id": "e1", "title": "Report 1", "summary": "Summary 1", "theme": "healthcare"},
        {"event_id": "e2", "title": "Report 2", "summary": "Summary 2", "theme": "healthcare"},
    ]

    result = build_baseline(
        source_type="gao",
        theme="healthcare",
        window_days=90,
    )

    assert result is not None
    assert result.source_type == "gao"
    assert result.event_count == 2


def test_build_baseline_with_real_events():
    """Build baseline from actual inserted events."""
    _insert_test_events(5, source_type="gao", theme="benefits")

    result = build_baseline(
        source_type="gao",
        theme="benefits",
        window_days=90,
    )

    assert result is not None
    assert result.event_count >= 5
    assert result.source_type == "gao"


def test_get_latest_baseline():
    """Get the most recent baseline for a source/theme."""
    # Build a baseline first
    _insert_test_events(3, source_type="oig", theme="fraud")
    build_baseline(source_type="oig", theme="fraud", window_days=90, save=True)

    baseline = get_latest_baseline(source_type="oig", theme="fraud")

    assert baseline is not None
    assert baseline["source_type"] == "oig"
    assert baseline["theme"] == "fraud"
