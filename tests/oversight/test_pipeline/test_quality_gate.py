"""Tests for quality gate."""

from src.oversight.agents.base import TimestampResult
from src.oversight.pipeline.quality_gate import (
    check_quality_gate,
)


def test_quality_gate_passes_with_pub_timestamp():
    timestamps = TimestampResult(
        pub_timestamp="2026-01-20T10:00:00Z",
        pub_precision="datetime",
        pub_source="extracted",
    )

    result = check_quality_gate(timestamps, url="https://example.com")

    assert result.passed is True
    assert result.rejection_reason is None


def test_quality_gate_passes_with_date_only():
    timestamps = TimestampResult(
        pub_timestamp="2026-01-20",
        pub_precision="date",
        pub_source="extracted",
    )

    result = check_quality_gate(timestamps, url="https://example.com")

    assert result.passed is True


def test_quality_gate_fails_without_pub_timestamp():
    timestamps = TimestampResult(
        pub_timestamp=None,
        pub_precision="unknown",
        pub_source="missing",
    )

    result = check_quality_gate(timestamps, url="https://example.com")

    assert result.passed is False
    assert result.rejection_reason == "temporal_incomplete"


def test_quality_gate_fails_with_unknown_precision_no_timestamp():
    timestamps = TimestampResult(
        pub_timestamp=None,
        pub_precision="unknown",
        pub_source="missing",
    )

    result = check_quality_gate(timestamps, url="https://example.com")

    assert result.passed is False


def test_quality_gate_fails_with_unknown_precision_and_timestamp():
    """Reject events where timestamp exists but precision is unknown."""
    timestamps = TimestampResult(
        pub_timestamp="2026-01-20",
        pub_precision="unknown",
        pub_source="inferred",
    )

    result = check_quality_gate(timestamps, url="https://example.com")

    assert result.passed is False
    assert result.rejection_reason == "temporal_incomplete"
