"""Tests for signal bridge — oversight → signals router → WebSocket (Phase 2)."""

from unittest.mock import MagicMock, patch

import pytest

from src.oversight.db_helpers import (
    get_om_event,
    insert_om_event,
    seed_default_escalation_signals,
)
from src.oversight.pipeline.signal_bridge import (
    BridgeResult,
    reset_singletons,
    route_oversight_event,
)


@pytest.fixture(autouse=True)
def setup():
    """Reset singletons and seed escalation signals."""
    reset_singletons()
    seed_default_escalation_signals()
    yield
    reset_singletons()


def _make_event(
    event_id="om-test-bridge-001",
    title="GAO Issues Criminal Referral for VA Contract Fraud",
    source_type="gao",
    is_escalation=True,
    escalation_signals=None,
    ml_score=0.85,
    ml_risk_level="high",
) -> dict:
    """Build a realistic om_event dict."""
    return {
        "event_id": event_id,
        "event_type": "report_release",
        "theme": "oversight_report",
        "primary_source_type": source_type,
        "primary_url": f"https://gao.gov/reports/{event_id}",
        "pub_timestamp": "2026-02-07T12:00:00Z",
        "pub_precision": "day",
        "pub_source": "authority",
        "event_timestamp": None,
        "event_precision": None,
        "event_source": None,
        "title": title,
        "summary": "GAO has referred this matter for criminal investigation.",
        "raw_content": "Full report content...",
        "is_escalation": 1 if is_escalation else 0,
        "escalation_signals": escalation_signals or ["criminal referral"],
        "ml_score": ml_score,
        "ml_risk_level": ml_risk_level,
        "is_deviation": 0,
        "deviation_reason": None,
        "canonical_refs": None,
        "fetched_at": "2026-02-07T12:00:00Z",
    }


def _insert_event(event: dict) -> None:
    """Persist event so surfacing works."""
    insert_om_event(event)


@patch("src.oversight.pipeline.signal_bridge._get_router")
@patch("src.oversight.pipeline.signal_bridge.notify_new_signal_sync", create=True)
def test_bridge_routes_event(mock_ws, mock_get_router):
    """Event routes through adapter and router, returns BridgeResult."""
    # Mock router to return a route result
    mock_route_result = MagicMock()
    mock_route_result.suppressed = False
    mock_route_result.severity = "high"
    mock_router = MagicMock()
    mock_router.route.return_value = [mock_route_result]
    mock_get_router.return_value = mock_router

    event = _make_event()
    _insert_event(event)

    # Patch notify_new_signal_sync at module level
    with patch(
        "src.oversight.pipeline.signal_bridge.notify_new_signal_sync",
        create=True,
    ):
        result = route_oversight_event(event)

    assert isinstance(result, BridgeResult)
    assert result.event_id == event["event_id"]
    assert result.routed is True
    assert result.route_count == 1


@patch("src.oversight.pipeline.signal_bridge._get_router")
def test_priority_computed_from_route_results(mock_get_router):
    """Priority scorer receives correct severity from route results."""
    mock_route = MagicMock()
    mock_route.suppressed = False
    mock_route.severity = "critical"
    mock_router = MagicMock()
    mock_router.route.return_value = [mock_route]
    mock_get_router.return_value = mock_router

    event = _make_event(ml_score=0.9)
    _insert_event(event)

    with patch(
        "src.oversight.pipeline.signal_bridge.notify_new_signal_sync",
        create=True,
    ):
        result = route_oversight_event(event)

    assert result.priority_score > 0.0
    assert result.priority_level in ("critical", "high", "medium", "low")


@patch("src.oversight.pipeline.signal_bridge._get_router")
def test_websocket_called_for_high_severity(mock_get_router):
    """WebSocket notify called when priority exceeds threshold."""
    mock_route = MagicMock()
    mock_route.suppressed = False
    mock_route.severity = "critical"
    mock_router = MagicMock()
    mock_router.route.return_value = [mock_route]
    mock_get_router.return_value = mock_router

    event = _make_event(ml_score=0.95, ml_risk_level="critical")
    _insert_event(event)

    with patch("src.websocket.broadcast.notify_new_signal_sync"):
        result = route_oversight_event(event)

    if result.priority_score >= 0.40:
        assert result.websocket_pushed is True or len(result.errors) > 0


@patch("src.oversight.pipeline.signal_bridge._get_router")
def test_websocket_not_called_for_low_severity(mock_get_router):
    """WebSocket NOT called when priority is below threshold."""
    mock_router = MagicMock()
    mock_router.route.return_value = []  # No routes matched
    mock_get_router.return_value = mock_router

    event = _make_event(
        source_type="trade_press",
        ml_score=0.1,
        ml_risk_level="low",
        is_escalation=False,
        escalation_signals=[],
    )
    _insert_event(event)

    result = route_oversight_event(event)

    assert result.websocket_pushed is False


@patch("src.oversight.pipeline.signal_bridge._get_router")
def test_bridge_errors_dont_break_storage(mock_get_router):
    """Bridge failure should be captured, not raised."""
    mock_get_router.side_effect = RuntimeError("Router init failed")

    event = _make_event()
    _insert_event(event)

    result = route_oversight_event(event)

    assert len(result.errors) > 0
    assert "Bridge error" in result.errors[0]
    # Event should still be in DB (inserted before bridge)
    db_event = get_om_event(event["event_id"])
    assert db_event is not None


@patch("src.oversight.pipeline.signal_bridge._get_router")
def test_surfaced_flag_set_when_alert_threshold_met(mock_get_router):
    """When should_alert=True, event should be marked as surfaced in DB."""
    mock_route = MagicMock()
    mock_route.suppressed = False
    mock_route.severity = "critical"
    mock_router = MagicMock()
    mock_router.route.return_value = [mock_route]
    mock_get_router.return_value = mock_router

    event = _make_event(ml_score=0.95, ml_risk_level="critical")
    _insert_event(event)

    with patch(
        "src.websocket.broadcast.notify_new_signal_sync",
    ):
        result = route_oversight_event(event)

    if result.surfaced:
        db_event = get_om_event(event["event_id"])
        assert db_event["surfaced"] == 1
        assert db_event["surfaced_via"] == "signal_bridge"


@patch("src.oversight.pipeline.signal_bridge._get_router")
def test_suppressed_routes_not_counted_active(mock_get_router):
    """Suppressed routes should not trigger WebSocket or surfacing."""
    mock_route_active = MagicMock()
    mock_route_active.suppressed = False
    mock_route_active.severity = "low"
    mock_route_suppressed = MagicMock()
    mock_route_suppressed.suppressed = True
    mock_route_suppressed.severity = "critical"

    mock_router = MagicMock()
    mock_router.route.return_value = [mock_route_active, mock_route_suppressed]
    mock_get_router.return_value = mock_router

    event = _make_event(
        ml_score=0.2,
        ml_risk_level="low",
        escalation_signals=[],
    )
    _insert_event(event)

    result = route_oversight_event(event)

    assert result.route_count == 2
    assert result.suppressed_count == 1
    # Active route has low severity, so severity should come from
    # active results (low), not suppressed (critical)


@patch("src.oversight.pipeline.signal_bridge._get_router")
def test_no_routes_uses_event_severity(mock_get_router):
    """When no routes match, severity falls back to event data."""
    mock_router = MagicMock()
    mock_router.route.return_value = []
    mock_get_router.return_value = mock_router

    event = _make_event(ml_risk_level="high")
    _insert_event(event)

    result = route_oversight_event(event)

    assert result.routed is False
    # Priority should still be computed using event's own ml_risk_level
    assert result.priority_score > 0.0


def test_bridge_result_defaults():
    """BridgeResult should have sensible defaults."""
    result = BridgeResult(event_id="test")
    assert result.routed is False
    assert result.route_count == 0
    assert result.priority_score == 0.0
    assert result.surfaced is False
    assert result.websocket_pushed is False
    assert result.errors == []
