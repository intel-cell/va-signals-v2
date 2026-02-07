"""Tests for get_signals_by_state severity filter fix (Phase 0)."""

import pytest

from src.state.db_helpers import (
    get_signals_by_state,
    insert_state_classification,
    insert_state_signal,
    insert_state_source,
)


@pytest.fixture(autouse=True)
def seed_data():
    """Seed a source, signals, and classifications for testing."""
    insert_state_source(
        {
            "source_id": "tx_test",
            "state": "TX",
            "source_type": "official",
            "name": "Test TX Source",
            "url": "https://example.com",
        }
    )
    insert_state_source(
        {
            "source_id": "ca_test",
            "state": "CA",
            "source_type": "official",
            "name": "Test CA Source",
            "url": "https://example.com",
        }
    )

    insert_state_signal(
        {
            "signal_id": "sig-tx-1",
            "state": "TX",
            "source_id": "tx_test",
            "title": "TX High Signal",
            "url": "https://example.com/tx1",
        }
    )
    insert_state_signal(
        {
            "signal_id": "sig-tx-2",
            "state": "TX",
            "source_id": "tx_test",
            "title": "TX Low Signal",
            "url": "https://example.com/tx2",
        }
    )
    insert_state_signal(
        {
            "signal_id": "sig-ca-1",
            "state": "CA",
            "source_id": "ca_test",
            "title": "CA High Signal",
            "url": "https://example.com/ca1",
        }
    )

    insert_state_classification(
        {
            "signal_id": "sig-tx-1",
            "severity": "high",
            "classification_method": "keyword",
        }
    )
    insert_state_classification(
        {
            "signal_id": "sig-tx-2",
            "severity": "low",
            "classification_method": "keyword",
        }
    )
    insert_state_classification(
        {
            "signal_id": "sig-ca-1",
            "severity": "high",
            "classification_method": "keyword",
        }
    )
    yield


def test_state_filter_only():
    """Filter by state alone still works."""
    results = get_signals_by_state(state="TX")
    assert len(results) == 2
    assert all(r["state"] == "TX" for r in results)


def test_severity_filter_only():
    """Filter by severity alone (state=None)."""
    results = get_signals_by_state(severity="high")
    assert len(results) == 2
    assert all(r["severity"] == "high" for r in results)


def test_state_and_severity():
    """Combined state + severity filter."""
    results = get_signals_by_state(state="TX", severity="high")
    assert len(results) == 1
    assert results[0]["signal_id"] == "sig-tx-1"
    assert results[0]["severity"] == "high"


def test_no_filters_returns_all():
    """No filters returns all signals."""
    results = get_signals_by_state()
    assert len(results) == 3


def test_severity_no_match():
    """Severity filter with no matching classification."""
    results = get_signals_by_state(severity="critical")
    assert len(results) == 0
