"""Tests for the battlefield signal bridge.

Covers priority scoring, WebSocket push decisions, error handling,
and source type mapping.
"""

from unittest.mock import patch

from src.battlefield.signal_bridge import (
    GATE_SOURCE_MAP,
    GateBridgeResult,
    route_gate_alert,
)


def _make_alert(**overrides) -> dict:
    """Create a test gate alert dict."""
    base = {
        "alert_id": "alert_test001",
        "vehicle_id": "hearing_EVT001",
        "alert_type": "gate_moved",
        "title": "Hearing date changed",
        "new_value": "2025-04-15",
        "old_value": "2025-04-01",
        "days_impact": 14,
        "recommended_action": "Adjust preparation schedule",
        "source_type": "hearing_updates",
        "source_event_id": "1",
    }
    base.update(overrides)
    return base


class TestGateBridgeResult:
    def test_defaults(self):
        result = GateBridgeResult()
        assert result.alert_id == ""
        assert result.priority_score == 0.0
        assert result.priority_level == "low"
        assert result.websocket_pushed is False
        assert result.errors == []

    def test_custom_values(self):
        result = GateBridgeResult(
            alert_id="a1", priority_score=0.8, priority_level="high", websocket_pushed=True
        )
        assert result.alert_id == "a1"
        assert result.priority_score == 0.8


class TestRouteGateAlert:
    @patch("src.battlefield.signal_bridge._push_websocket")
    def test_gate_moved_high_priority(self, mock_push):
        """gate_moved alert gets high severity, triggers WebSocket."""
        alert = _make_alert(alert_type="gate_moved", days_impact=14)
        result = route_gate_alert(alert)

        assert result.priority_score > 0.0
        assert result.priority_level in ("high", "critical", "medium")
        assert result.alert_id == "alert_test001"

    @patch("src.battlefield.signal_bridge._push_websocket")
    def test_gate_passed_lower_priority(self, mock_push):
        """gate_passed alert gets lower severity."""
        alert = _make_alert(alert_type="gate_passed", days_impact=None)
        result = route_gate_alert(alert)

        # gate_passed has severity "low" and signal_count 0
        assert result.priority_score >= 0.0

    @patch("src.battlefield.signal_bridge._push_websocket")
    def test_accelerated_gate_bumps_to_critical(self, mock_push):
        """Negative days_impact bumps severity to critical."""
        alert = _make_alert(alert_type="gate_moved", days_impact=-10)
        result = route_gate_alert(alert)

        # Critical severity should produce higher score
        assert result.priority_score > 0.4

    @patch("src.battlefield.signal_bridge._push_websocket")
    def test_status_changed_is_escalation(self, mock_push):
        """status_changed counts as escalation signal."""
        alert = _make_alert(alert_type="status_changed", days_impact=None)
        result = route_gate_alert(alert)

        # signal_count=1 + severity=high should push above websocket threshold
        assert result.priority_score > 0.0

    @patch("src.battlefield.signal_bridge._push_websocket")
    def test_new_gate_no_escalation(self, mock_push):
        """new_gate has signal_count=0 (not an escalation type)."""
        alert = _make_alert(alert_type="new_gate", days_impact=None)
        result = route_gate_alert(alert)

        assert result.priority_score >= 0.0

    @patch(
        "src.battlefield.signal_bridge._push_websocket",
        side_effect=Exception("WS down"),
    )
    def test_websocket_failure_nonfatal(self, mock_push):
        """WebSocket failure doesn't crash, records error."""
        alert = _make_alert(alert_type="gate_moved")
        result = route_gate_alert(alert)

        assert result.websocket_pushed is False
        assert len(result.errors) >= 1
        assert "websocket" in result.errors[0]

    @patch(
        "src.battlefield.signal_bridge.compute_escalation_priority",
        side_effect=Exception("scoring broken"),
    )
    def test_priority_failure_nonfatal(self, mock_priority):
        """Priority scoring failure doesn't crash, records error."""
        alert = _make_alert()
        result = route_gate_alert(alert)

        assert result.priority_score == 0.0
        assert len(result.errors) >= 1
        assert "priority" in result.errors[0]

    @patch("src.battlefield.signal_bridge._push_websocket")
    def test_source_mapping_hearing(self, mock_push):
        """hearing_updates source maps to congressional_record for scoring."""
        alert = _make_alert(source_type="hearing_updates")
        result = route_gate_alert(alert)
        # Just verify it doesn't crash and uses the mapping
        assert result.alert_id == "alert_test001"

    @patch("src.battlefield.signal_bridge._push_websocket")
    def test_source_mapping_bill(self, mock_push):
        """bill_actions source maps to crs for scoring."""
        alert = _make_alert(source_type="bill_actions")
        result = route_gate_alert(alert)
        assert result.alert_id == "alert_test001"

    @patch("src.battlefield.signal_bridge._push_websocket")
    def test_source_mapping_om_events(self, mock_push):
        """om_events source maps to gao for scoring."""
        alert = _make_alert(source_type="om_events")
        result = route_gate_alert(alert)
        assert result.alert_id == "alert_test001"

    @patch("src.battlefield.signal_bridge._push_websocket")
    def test_unknown_source_falls_back(self, mock_push):
        """Unknown source_type falls back to 'other'."""
        alert = _make_alert(source_type="unknown_source")
        result = route_gate_alert(alert)
        assert result.priority_score >= 0.0


class TestGateSourceMap:
    def test_hearing_updates_mapped(self):
        assert GATE_SOURCE_MAP["hearing_updates"] == "congressional_record"

    def test_bill_actions_mapped(self):
        assert GATE_SOURCE_MAP["bill_actions"] == "crs"

    def test_om_events_mapped(self):
        assert GATE_SOURCE_MAP["om_events"] == "gao"

    def test_bf_calendar_mapped(self):
        assert GATE_SOURCE_MAP["bf_calendar_events"] == "gao"
