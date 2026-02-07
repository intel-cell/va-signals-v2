"""
Gate Detection Tests

Tests the battlefield gate detection system:
- Pure helper functions (no DB)
- Detection functions (DB mocked)
"""

from unittest.mock import patch

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

# ---------------------------------------------------------------------------
# _parse_date
# ---------------------------------------------------------------------------


class TestParseDate:
    def test_valid_date(self):
        result = _parse_date("2024-01-15")
        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_none_input(self):
        assert _parse_date(None) is None

    def test_empty_string(self):
        assert _parse_date("") is None

    def test_invalid_string(self):
        assert _parse_date("not-a-date") is None

    def test_date_with_time_suffix(self):
        result = _parse_date("2024-06-30T12:00:00")
        assert result is not None
        assert result.day == 30


# ---------------------------------------------------------------------------
# _days_between
# ---------------------------------------------------------------------------


class TestDaysBetween:
    def test_positive_delayed(self):
        assert _days_between("2024-01-10", "2024-01-15") == 5

    def test_negative_accelerated(self):
        assert _days_between("2024-01-15", "2024-01-10") == -5

    def test_zero_same_date(self):
        assert _days_between("2024-01-15", "2024-01-15") == 0

    def test_none_when_old_invalid(self):
        assert _days_between(None, "2024-01-15") is None

    def test_none_when_new_invalid(self):
        assert _days_between("2024-01-15", None) is None

    def test_none_when_both_invalid(self):
        assert _days_between(None, None) is None

    def test_large_gap(self):
        assert _days_between("2024-01-01", "2024-12-31") == 365


# ---------------------------------------------------------------------------
# _recommend_date_action
# ---------------------------------------------------------------------------


class TestRecommendDateAction:
    def test_none_days(self):
        result = _recommend_date_action(None)
        assert "Review date change" in result

    def test_significant_delay(self):
        result = _recommend_date_action(21)
        assert "Significant delay" in result

    def test_moderate_delay(self):
        result = _recommend_date_action(10)
        assert "Moderate delay" in result

    def test_minor_delay(self):
        result = _recommend_date_action(3)
        assert "Minor delay" in result

    def test_accelerated_large(self):
        result = _recommend_date_action(-10)
        assert "ACCELERATED" in result

    def test_accelerated_small(self):
        result = _recommend_date_action(-3)
        assert "Accelerated" in result

    def test_no_change(self):
        result = _recommend_date_action(0)
        assert "No change" in result

    def test_boundary_14_is_moderate(self):
        # 14 is not > 14, so it should be moderate
        result = _recommend_date_action(14)
        assert "Moderate delay" in result

    def test_boundary_15_is_significant(self):
        result = _recommend_date_action(15)
        assert "Significant delay" in result

    def test_boundary_7_is_minor(self):
        # 7 is not > 7, so it should be minor
        result = _recommend_date_action(7)
        assert "Minor delay" in result


# ---------------------------------------------------------------------------
# _recommend_status_action
# ---------------------------------------------------------------------------


class TestRecommendStatusAction:
    def test_cancelled(self):
        result = _recommend_status_action("Scheduled", "Cancelled")
        assert "cancelled" in result.lower()

    def test_postponed(self):
        result = _recommend_status_action("Scheduled", "Postponed")
        assert "postponed" in result.lower()

    def test_rescheduled(self):
        result = _recommend_status_action("Postponed", "Rescheduled")
        assert "rescheduled" in result.lower()

    def test_scheduled(self):
        result = _recommend_status_action(None, "Scheduled")
        assert "scheduled" in result.lower()

    def test_other_status(self):
        result = _recommend_status_action("Active", "Unknown")
        assert "Status changed" in result


# ---------------------------------------------------------------------------
# detect_hearing_changes (mocked DB)
# ---------------------------------------------------------------------------


class TestDetectHearingChanges:
    @patch("src.battlefield.gate_detection.create_gate_alert")
    @patch("src.battlefield.gate_detection._execute")
    def test_no_updates_returns_zeros(self, mock_exec, mock_alert):
        mock_exec.return_value = []
        result = detect_hearing_changes()
        assert result["new_hearings"] == 0
        assert result["date_changes"] == 0
        assert result["status_changes"] == 0
        assert result["alerts_created"] == 0
        mock_alert.assert_not_called()

    @patch("src.battlefield.gate_detection.create_gate_alert")
    @patch("src.battlefield.gate_detection._execute")
    def test_date_change_creates_alert(self, mock_exec, mock_alert):
        mock_exec.side_effect = [
            [
                {
                    "id": 1,
                    "event_id": "h001",
                    "field_changed": "hearing_date",
                    "old_value": "2024-01-10",
                    "new_value": "2024-01-20",
                    "detected_at": "2024-01-15",
                    "title": "VA Hearing",
                    "hearing_date": "2024-01-20",
                    "status": "Scheduled",
                }
            ],
            [],  # new hearings query
        ]
        result = detect_hearing_changes()
        assert result["date_changes"] == 1
        assert result["alerts_created"] == 1
        mock_alert.assert_called_once()
        call_kwargs = mock_alert.call_args
        assert (
            call_kwargs[1]["alert_type"] == "gate_moved"
            or call_kwargs.kwargs.get("alert_type") == "gate_moved"
        )

    @patch("src.battlefield.gate_detection.create_gate_alert")
    @patch("src.battlefield.gate_detection._execute")
    def test_status_change_creates_alert(self, mock_exec, mock_alert):
        mock_exec.side_effect = [
            [
                {
                    "id": 2,
                    "event_id": "h002",
                    "field_changed": "status",
                    "old_value": "Scheduled",
                    "new_value": "Cancelled",
                    "detected_at": "2024-01-15",
                    "title": "VA Hearing",
                    "hearing_date": "2024-01-20",
                    "status": "Cancelled",
                }
            ],
            [],  # new hearings query
        ]
        result = detect_hearing_changes()
        assert result["status_changes"] == 1
        assert result["alerts_created"] == 1

    @patch("src.battlefield.gate_detection.create_gate_alert")
    @patch("src.battlefield.gate_detection._execute")
    def test_new_hearing_creates_alert(self, mock_exec, mock_alert):
        mock_exec.side_effect = [
            [],  # no updates
            [
                {
                    "event_id": "h003",
                    "title": "New VA Hearing",
                    "hearing_date": "2024-02-01",
                    "committee_name": "SVAC",
                }
            ],
        ]
        result = detect_hearing_changes()
        assert result["new_hearings"] == 1
        assert result["alerts_created"] == 1


# ---------------------------------------------------------------------------
# detect_bill_status_changes (mocked DB)
# ---------------------------------------------------------------------------


class TestDetectBillStatusChanges:
    @patch("src.battlefield.gate_detection.create_gate_alert")
    @patch("src.battlefield.gate_detection._execute")
    def test_no_actions_returns_zeros(self, mock_exec, mock_alert):
        mock_exec.return_value = []
        result = detect_bill_status_changes()
        assert result["status_changes"] == 0
        assert result["alerts_created"] == 0

    @patch("src.battlefield.gate_detection.create_gate_alert")
    @patch("src.battlefield.gate_detection._execute")
    def test_passed_action_creates_alert(self, mock_exec, mock_alert):
        mock_exec.return_value = [
            {
                "id": 10,
                "bill_id": "hr1234",
                "action_date": "2024-01-20",
                "action_text": "Passed House by voice vote",
                "action_type": "Floor",
                "title": "Veterans Act",
                "bill_type": "hr",
                "bill_number": "1234",
            }
        ]
        result = detect_bill_status_changes()
        assert result["status_changes"] == 1
        assert result["alerts_created"] == 1

    @patch("src.battlefield.gate_detection.create_gate_alert")
    @patch("src.battlefield.gate_detection._execute")
    def test_non_significant_action_ignored(self, mock_exec, mock_alert):
        mock_exec.return_value = [
            {
                "id": 11,
                "bill_id": "hr5678",
                "action_date": "2024-01-20",
                "action_text": "Referred to committee",
                "action_type": "IntroReferral",
                "title": "Some Bill",
                "bill_type": "hr",
                "bill_number": "5678",
            }
        ]
        result = detect_bill_status_changes()
        assert result["status_changes"] == 0
        assert result["alerts_created"] == 0
        mock_alert.assert_not_called()


# ---------------------------------------------------------------------------
# detect_oversight_escalations (mocked DB)
# ---------------------------------------------------------------------------


class TestDetectOversightEscalations:
    @patch("src.battlefield.gate_detection.create_gate_alert")
    @patch("src.battlefield.gate_detection._execute")
    def test_escalation_creates_alert(self, mock_exec, mock_alert):
        mock_exec.return_value = [
            {
                "event_id": "om001",
                "title": "GAO Report on VA",
                "primary_source_type": "gao",
                "pub_timestamp": "2024-01-20",
                "is_escalation": 1,
                "is_deviation": 0,
                "escalation_signals": "bipartisan",
                "deviation_reason": None,
            }
        ]
        result = detect_oversight_escalations()
        assert result["escalations"] == 1
        assert result["deviations"] == 0
        assert result["alerts_created"] == 1

    @patch("src.battlefield.gate_detection.create_gate_alert")
    @patch("src.battlefield.gate_detection._execute")
    def test_deviation_creates_alert(self, mock_exec, mock_alert):
        mock_exec.return_value = [
            {
                "event_id": "om002",
                "title": "OIG Report",
                "primary_source_type": "oig",
                "pub_timestamp": "2024-01-20",
                "is_escalation": 0,
                "is_deviation": 1,
                "escalation_signals": None,
                "deviation_reason": "Unexpected finding",
            }
        ]
        result = detect_oversight_escalations()
        assert result["escalations"] == 0
        assert result["deviations"] == 1
        assert result["alerts_created"] == 1

    @patch("src.battlefield.gate_detection.create_gate_alert")
    @patch("src.battlefield.gate_detection._execute")
    def test_both_escalation_and_deviation(self, mock_exec, mock_alert):
        mock_exec.return_value = [
            {
                "event_id": "om003",
                "title": "Critical Report",
                "primary_source_type": "gao",
                "pub_timestamp": "2024-01-20",
                "is_escalation": 1,
                "is_deviation": 1,
                "escalation_signals": "urgent",
                "deviation_reason": "Major deviation",
            }
        ]
        result = detect_oversight_escalations()
        assert result["escalations"] == 1
        assert result["deviations"] == 1
        assert result["alerts_created"] == 2

    @patch("src.battlefield.gate_detection.create_gate_alert")
    @patch("src.battlefield.gate_detection._execute")
    def test_no_escalations_returns_zeros(self, mock_exec, mock_alert):
        mock_exec.return_value = []
        result = detect_oversight_escalations()
        assert result["escalations"] == 0
        assert result["deviations"] == 0
        assert result["alerts_created"] == 0


# ---------------------------------------------------------------------------
# detect_passed_gates (mocked DB)
# ---------------------------------------------------------------------------


class TestDetectPassedGates:
    @patch("src.battlefield.gate_detection.create_gate_alert")
    @patch("src.battlefield.gate_detection._execute_write")
    @patch("src.battlefield.gate_detection._execute")
    def test_past_event_marked_passed(self, mock_exec, mock_write, mock_alert):
        mock_exec.return_value = [
            {
                "event_id": "ev001",
                "vehicle_id": "v001",
                "date": "2024-01-01",
                "title": "Committee Vote",
            }
        ]
        result = detect_passed_gates()
        assert result["marked_passed"] == 1
        mock_write.assert_called_once()
        mock_alert.assert_called_once()

    @patch("src.battlefield.gate_detection.create_gate_alert")
    @patch("src.battlefield.gate_detection._execute_write")
    @patch("src.battlefield.gate_detection._execute")
    def test_no_events_returns_zero(self, mock_exec, mock_write, mock_alert):
        mock_exec.return_value = []
        result = detect_passed_gates()
        assert result["marked_passed"] == 0
        mock_write.assert_not_called()
        mock_alert.assert_not_called()


# ---------------------------------------------------------------------------
# run_all_detections (mocked sub-functions)
# ---------------------------------------------------------------------------


class TestRunAllDetections:
    @patch("src.battlefield.gate_detection.detect_passed_gates")
    @patch("src.battlefield.gate_detection.detect_oversight_escalations")
    @patch("src.battlefield.gate_detection.detect_bill_status_changes")
    @patch("src.battlefield.gate_detection.detect_hearing_changes")
    def test_calls_all_four_detections(self, mock_hear, mock_bill, mock_over, mock_pass):
        mock_hear.return_value = {"alerts_created": 1}
        mock_bill.return_value = {"alerts_created": 2}
        mock_over.return_value = {"alerts_created": 0}
        mock_pass.return_value = {"alerts_created": 0, "marked_passed": 0}

        result = run_all_detections()

        mock_hear.assert_called_once()
        mock_bill.assert_called_once()
        mock_over.assert_called_once()
        mock_pass.assert_called_once()
        assert "hearings" in result
        assert "bills" in result
        assert "oversight" in result
        assert "passed_gates" in result
