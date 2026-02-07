"""Tests for battlefield gate detection module.

Covers all 4 detection functions, helper functions, and the
_create_and_route_alert bridge wrapper.
"""

from datetime import datetime, timedelta
from unittest.mock import patch

from src.battlefield.db_helpers import (
    upsert_calendar_event,
    upsert_vehicle,
)
from src.battlefield.gate_detection import (
    _days_between,
    _parse_date,
    _recommend_date_action,
    _recommend_status_action,
    detect_bill_status_changes,
    detect_hearing_changes,
    detect_oversight_escalations,
    detect_passed_gates,
    run_all_detections,
)
from src.db import connect
from src.db import execute as db_execute

# ── Helpers ──────────────────────────────────────────────────────────


def _seed_vehicle(vehicle_id: str, title: str = "Test Vehicle") -> str:
    """Seed a vehicle so FK joins succeed."""
    return upsert_vehicle(
        vehicle_id=vehicle_id,
        vehicle_type="bill",
        title=title,
        identifier="TEST-001",
        current_stage="committee",
        status_date=datetime.utcnow().isoformat(),
    )


def _insert_hearing(event_id: str, title: str, hearing_date: str, status: str = "Scheduled"):
    """Insert a hearing record."""
    conn = connect()
    now = datetime.utcnow().isoformat()
    db_execute(
        conn,
        """
        INSERT OR IGNORE INTO hearings (
            event_id, congress, chamber, committee_code, committee_name,
            hearing_date, title, status, first_seen_at, updated_at
        ) VALUES (
            :event_id, 119, 'House', 'HVAC', 'HVAC',
            :hearing_date, :title, :status, :first_seen, :updated_at
        )
        """,
        {
            "event_id": event_id,
            "title": title,
            "hearing_date": hearing_date,
            "status": status,
            "first_seen": now,
            "updated_at": now,
        },
    )
    conn.commit()


def _insert_hearing_update(event_id: str, field_changed: str, old_value: str, new_value: str):
    """Insert a hearing update record."""
    conn = connect()
    db_execute(
        conn,
        """
        INSERT INTO hearing_updates (event_id, field_changed, old_value, new_value, detected_at)
        VALUES (:event_id, :field_changed, :old_value, :new_value, :detected_at)
        """,
        {
            "event_id": event_id,
            "field_changed": field_changed,
            "old_value": old_value,
            "new_value": new_value,
            "detected_at": datetime.utcnow().isoformat(),
        },
    )
    conn.commit()


def _insert_bill(bill_id: str, title: str, bill_type: str = "hr", bill_number: int = 1):
    """Insert a bill record."""
    conn = connect()
    now = datetime.utcnow().isoformat()
    db_execute(
        conn,
        """
        INSERT OR IGNORE INTO bills (bill_id, title, bill_type, bill_number, congress, first_seen_at, updated_at)
        VALUES (:bill_id, :title, :bill_type, :bill_number, 119, :first_seen, :updated_at)
        """,
        {
            "bill_id": bill_id,
            "title": title,
            "bill_type": bill_type,
            "bill_number": bill_number,
            "first_seen": now,
            "updated_at": now,
        },
    )
    conn.commit()


def _insert_bill_action(bill_id: str, action_text: str, action_type: str = "Floor"):
    """Insert a bill action record."""
    conn = connect()
    db_execute(
        conn,
        """
        INSERT INTO bill_actions (bill_id, action_date, action_text, action_type, first_seen_at)
        VALUES (:bill_id, :action_date, :action_text, :action_type, :first_seen)
        """,
        {
            "bill_id": bill_id,
            "action_date": datetime.utcnow().date().isoformat(),
            "action_text": action_text,
            "action_type": action_type,
            "first_seen": datetime.utcnow().isoformat(),
        },
    )
    conn.commit()


def _insert_om_event(
    event_id: str,
    title: str,
    is_escalation: int = 0,
    is_deviation: int = 0,
    deviation_reason: str | None = None,
):
    """Insert an oversight monitor event."""
    conn = connect()
    now = datetime.utcnow().isoformat()
    db_execute(
        conn,
        """
        INSERT INTO om_events (
            event_id, event_type, title, primary_source_type, primary_url,
            pub_timestamp, pub_precision, pub_source,
            is_escalation, is_deviation, deviation_reason,
            created_at, fetched_at, raw_content
        ) VALUES (
            :event_id, 'report', :title, 'gao', 'https://example.com',
            :pub_ts, 'day', 'authority',
            :is_escalation, :is_deviation, :deviation_reason,
            :created_at, :created_at, 'raw'
        )
        """,
        {
            "event_id": event_id,
            "title": title,
            "pub_ts": now,
            "is_escalation": is_escalation,
            "is_deviation": is_deviation,
            "deviation_reason": deviation_reason,
            "created_at": now,
        },
    )
    conn.commit()


# ── _parse_date tests ────────────────────────────────────────────────


class TestParseDate:
    def test_valid_date(self):
        result = _parse_date("2025-03-15")
        assert result == datetime(2025, 3, 15)

    def test_valid_date_with_time(self):
        result = _parse_date("2025-03-15T10:30:00")
        assert result == datetime(2025, 3, 15)

    def test_none(self):
        assert _parse_date(None) is None

    def test_empty_string(self):
        assert _parse_date("") is None

    def test_invalid_format(self):
        assert _parse_date("not-a-date") is None


# ── _days_between tests ──────────────────────────────────────────────


class TestDaysBetween:
    def test_delayed(self):
        result = _days_between("2025-03-01", "2025-03-15")
        assert result == 14

    def test_accelerated(self):
        result = _days_between("2025-03-15", "2025-03-01")
        assert result == -14

    def test_same_date(self):
        assert _days_between("2025-03-15", "2025-03-15") == 0

    def test_none_old(self):
        assert _days_between(None, "2025-03-15") is None

    def test_none_new(self):
        assert _days_between("2025-03-15", None) is None


# ── _recommend_date_action tests ─────────────────────────────────────


class TestRecommendDateAction:
    def test_none_days(self):
        assert "Review" in _recommend_date_action(None)

    def test_significant_delay(self):
        result = _recommend_date_action(20)
        assert "Significant delay" in result

    def test_moderate_delay(self):
        result = _recommend_date_action(10)
        assert "Moderate delay" in result

    def test_minor_delay(self):
        result = _recommend_date_action(3)
        assert "Minor delay" in result

    def test_accelerated(self):
        result = _recommend_date_action(-3)
        assert "Accelerated" in result

    def test_highly_accelerated(self):
        result = _recommend_date_action(-10)
        assert "ACCELERATED" in result

    def test_no_change(self):
        result = _recommend_date_action(0)
        assert "No change" in result


# ── _recommend_status_action tests ───────────────────────────────────


class TestRecommendStatusAction:
    def test_cancelled(self):
        result = _recommend_status_action("Scheduled", "Cancelled")
        assert "cancelled" in result.lower()

    def test_postponed(self):
        result = _recommend_status_action("Scheduled", "Postponed")
        assert "postponed" in result.lower()

    def test_rescheduled(self):
        result = _recommend_status_action("Cancelled", "Rescheduled to March")
        assert "rescheduled" in result.lower()

    def test_scheduled(self):
        result = _recommend_status_action(None, "Scheduled")
        assert "scheduled" in result.lower()

    def test_unknown(self):
        result = _recommend_status_action("A", "B")
        assert "Status changed" in result


# ── detect_hearing_changes tests ─────────────────────────────────────


class TestDetectHearingChanges:
    @patch("src.battlefield.signal_bridge.route_gate_alert", return_value=None)
    def test_hearing_date_change(self, mock_route):
        """Hearing date change creates gate_moved alert."""
        _seed_vehicle("hearing_EVT001")
        _insert_hearing("EVT001", "VA Benefits Hearing", "2025-04-01")
        _insert_hearing_update("EVT001", "hearing_date", "2025-03-15", "2025-04-01")

        stats = detect_hearing_changes()
        assert stats["date_changes"] >= 1
        assert stats["alerts_created"] >= 1

    @patch("src.battlefield.signal_bridge.route_gate_alert", return_value=None)
    def test_hearing_status_change(self, mock_route):
        """Hearing status change creates status_changed alert."""
        _seed_vehicle("hearing_EVT002")
        _insert_hearing("EVT002", "Claims Oversight Hearing", "2025-05-01")
        _insert_hearing_update("EVT002", "status", "Scheduled", "Cancelled")

        stats = detect_hearing_changes()
        assert stats["status_changes"] >= 1
        assert stats["alerts_created"] >= 1

    def test_no_updates(self):
        """Empty table returns zero alerts."""
        stats = detect_hearing_changes()
        assert stats["date_changes"] == 0
        assert stats["status_changes"] == 0
        assert stats["alerts_created"] == 0

    @patch("src.battlefield.signal_bridge.route_gate_alert", return_value=None)
    def test_new_hearing_detected(self, mock_route):
        """Newly added hearing with future date creates new_gate alert."""
        _seed_vehicle("hearing_EVT003")
        future = (datetime.utcnow() + timedelta(days=30)).date().isoformat()
        _insert_hearing("EVT003", "New Benefits Committee Hearing", future)

        stats = detect_hearing_changes()
        assert stats["new_hearings"] >= 1


# ── detect_bill_status_changes tests ─────────────────────────────────


class TestDetectBillStatusChanges:
    @patch("src.battlefield.signal_bridge.route_gate_alert", return_value=None)
    def test_significant_action_creates_alert(self, mock_route):
        """Bill action with 'passed' keyword triggers alert."""
        _seed_vehicle("bill_HR1234")
        _insert_bill("HR1234", "Veterans Benefits Act")
        _insert_bill_action("HR1234", "Passed House by voice vote")

        stats = detect_bill_status_changes()
        assert stats["status_changes"] >= 1
        assert stats["alerts_created"] >= 1

    def test_no_significant_action(self):
        """Routine action without significant keywords creates no alert."""
        _seed_vehicle("bill_HR5678")
        _insert_bill("HR5678", "Routine Bill", bill_number=5678)
        _insert_bill_action("HR5678", "Referred to subcommittee on health")

        stats = detect_bill_status_changes()
        assert stats["alerts_created"] == 0

    @patch("src.battlefield.signal_bridge.route_gate_alert", return_value=None)
    def test_markup_action(self, mock_route):
        """'Markup' keyword triggers alert."""
        _seed_vehicle("bill_HR9999")
        _insert_bill("HR9999", "Test Bill", bill_number=9999)
        _insert_bill_action("HR9999", "Ordered to be reported by markup session")

        stats = detect_bill_status_changes()
        assert stats["alerts_created"] >= 1


# ── detect_oversight_escalations tests ───────────────────────────────


class TestDetectOversightEscalations:
    @patch("src.battlefield.signal_bridge.route_gate_alert", return_value=None)
    def test_escalation_creates_alert(self, mock_route):
        """OM event with is_escalation=1 creates alert."""
        _seed_vehicle("om_OM001")
        _insert_om_event("OM001", "GAO Report on VA Disability Claims", is_escalation=1)

        stats = detect_oversight_escalations()
        assert stats["escalations"] >= 1
        assert stats["alerts_created"] >= 1

    @patch("src.battlefield.signal_bridge.route_gate_alert", return_value=None)
    def test_deviation_creates_alert(self, mock_route):
        """OM event with is_deviation=1 creates alert."""
        _seed_vehicle("om_OM002")
        _insert_om_event(
            "OM002",
            "Deviation in VA processing times",
            is_deviation=1,
            deviation_reason="Processing time deviation",
        )

        stats = detect_oversight_escalations()
        assert stats["deviations"] >= 1

    def test_no_escalations(self):
        """No escalation or deviation events returns zero."""
        stats = detect_oversight_escalations()
        assert stats["escalations"] == 0
        assert stats["deviations"] == 0


# ── detect_passed_gates tests ────────────────────────────────────────


class TestDetectPassedGates:
    @patch("src.battlefield.signal_bridge.route_gate_alert", return_value=None)
    def test_past_event_marked_passed(self, mock_route):
        """Calendar event with past date gets marked as passed."""
        vehicle_id = "bill_BF001"
        _seed_vehicle(vehicle_id)
        past_date = (datetime.utcnow() - timedelta(days=3)).date().isoformat()
        upsert_calendar_event(
            event_id="CAL001",
            vehicle_id=vehicle_id,
            date=past_date,
            event_type="hearing",
            title="Past Hearing Event",
        )

        stats = detect_passed_gates()
        assert stats["marked_passed"] >= 1

    def test_future_event_not_marked(self):
        """Calendar event with future date is not marked."""
        vehicle_id = "bill_BF002"
        _seed_vehicle(vehicle_id)
        future_date = (datetime.utcnow() + timedelta(days=30)).date().isoformat()
        upsert_calendar_event(
            event_id="CAL002",
            vehicle_id=vehicle_id,
            date=future_date,
            event_type="hearing",
            title="Future Hearing Event",
        )

        stats = detect_passed_gates()
        assert stats["marked_passed"] == 0


# ── run_all_detections tests ─────────────────────────────────────────


class TestRunAllDetections:
    def test_returns_all_sections(self):
        """run_all_detections returns dict with all four sections."""
        results = run_all_detections()
        assert "hearings" in results
        assert "bills" in results
        assert "oversight" in results
        assert "passed_gates" in results

    def test_result_structure(self):
        """Each section has expected keys."""
        results = run_all_detections()
        assert "alerts_created" in results["hearings"]
        assert "alerts_created" in results["bills"]
        assert "alerts_created" in results["oversight"]
        assert "marked_passed" in results["passed_gates"]


# ── _create_and_route_alert tests ────────────────────────────────────


class TestCreateAndRouteAlert:
    def test_alert_created_even_if_bridge_fails(self):
        """Alert is created in DB even when bridge raises."""
        from src.battlefield.gate_detection import _create_and_route_alert

        _seed_vehicle("test_v1")
        with patch(
            "src.battlefield.signal_bridge.route_gate_alert",
            side_effect=Exception("bridge down"),
        ):
            alert_id = _create_and_route_alert(
                vehicle_id="test_v1",
                alert_type="new_gate",
                new_value="Test alert",
                source_type="hearings",
                title="Test Title",
            )
        assert alert_id.startswith("alert_")

    @patch("src.battlefield.signal_bridge.route_gate_alert")
    def test_bridge_receives_alert_data(self, mock_route):
        """Bridge receives alert_id and kwargs."""
        _seed_vehicle("test_v2")
        from src.battlefield.gate_detection import _create_and_route_alert

        alert_id = _create_and_route_alert(
            vehicle_id="test_v2",
            alert_type="gate_moved",
            new_value="New date",
            old_value="Old date",
            days_impact=7,
            source_type="hearing_updates",
            title="Hearing moved",
        )

        mock_route.assert_called_once()
        call_args = mock_route.call_args[0][0]
        assert call_args["alert_id"] == alert_id
        assert call_args["alert_type"] == "gate_moved"
        assert call_args["title"] == "Hearing moved"
        assert call_args["days_impact"] == 7
