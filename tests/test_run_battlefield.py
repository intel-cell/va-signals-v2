"""Tests for src/run_battlefield.py — CLI runner for battlefield dashboard."""

from unittest.mock import patch

from src import run_battlefield

# ── run_sync ─────────────────────────────────────────────────────


class TestRunSync:
    @patch("src.run_battlefield.send_error_alert")
    @patch("src.run_battlefield.insert_source_run")
    @patch("src.battlefield.calendar.sync_all_sources")
    def test_success_path(self, mock_sync, mock_insert, mock_alert):
        mock_sync.return_value = {
            "hearings": {"created_vehicles": 3, "created_events": 5},
            "bills": {"created_vehicles": 1, "created_events": 2},
        }

        result = run_battlefield.run_sync.__wrapped__()

        assert result == mock_sync.return_value
        mock_insert.assert_called_once()
        run_record = mock_insert.call_args[0][0]
        assert run_record["source_id"] == "battlefield_sync"
        assert run_record["status"] == "SUCCESS"
        assert run_record["records_fetched"] == 11  # 3+5+1+2
        mock_alert.assert_not_called()

    @patch("src.run_battlefield.send_error_alert")
    @patch("src.run_battlefield.insert_source_run")
    @patch("src.battlefield.calendar.sync_all_sources")
    def test_error_path(self, mock_sync, mock_insert, mock_alert):
        mock_sync.side_effect = RuntimeError("Calendar API failure")

        result = run_battlefield.run_sync.__wrapped__()

        assert result == {}
        mock_insert.assert_called_once()
        run_record = mock_insert.call_args[0][0]
        assert run_record["status"] == "ERROR"
        assert any("Calendar API failure" in e for e in run_record["errors"])
        mock_alert.assert_called_once()

    @patch("src.run_battlefield.send_error_alert")
    @patch("src.run_battlefield.insert_source_run")
    @patch("src.battlefield.calendar.sync_all_sources")
    def test_insert_failure_does_not_raise(self, mock_sync, mock_insert, mock_alert):
        """If insert_source_run fails, run_sync should not crash."""
        mock_sync.return_value = {"hearings": {"created_vehicles": 1, "created_events": 0}}
        mock_insert.side_effect = RuntimeError("DB error")

        # Should not raise
        result = run_battlefield.run_sync.__wrapped__()
        assert "hearings" in result


# ── run_detection ────────────────────────────────────────────────


class TestRunDetection:
    @patch("src.run_battlefield.send_error_alert")
    @patch("src.run_battlefield.insert_source_run")
    @patch("src.battlefield.gate_detection.run_all_detections")
    def test_success_path(self, mock_detect, mock_insert, mock_alert):
        mock_detect.return_value = {
            "gate_moved": {"alerts_created": 2},
            "new_gate": {"alerts_created": 1},
        }

        result = run_battlefield.run_detection()

        assert result == mock_detect.return_value
        mock_insert.assert_called_once()
        run_record = mock_insert.call_args[0][0]
        assert run_record["source_id"] == "battlefield_detection"
        assert run_record["status"] == "SUCCESS"
        assert run_record["records_fetched"] == 3
        mock_alert.assert_not_called()

    @patch("src.run_battlefield.send_error_alert")
    @patch("src.run_battlefield.insert_source_run")
    @patch("src.battlefield.gate_detection.run_all_detections")
    def test_error_path(self, mock_detect, mock_insert, mock_alert):
        mock_detect.side_effect = RuntimeError("Detection engine failure")

        result = run_battlefield.run_detection()

        assert result == {}
        run_record = mock_insert.call_args[0][0]
        assert run_record["status"] == "ERROR"
        mock_alert.assert_called_once()

    @patch("src.run_battlefield.send_error_alert")
    @patch("src.run_battlefield.insert_source_run")
    @patch("src.battlefield.gate_detection.run_all_detections")
    def test_zero_alerts(self, mock_detect, mock_insert, mock_alert):
        mock_detect.return_value = {"gate_moved": {"alerts_created": 0}}

        run_battlefield.run_detection()

        run_record = mock_insert.call_args[0][0]
        assert run_record["status"] == "SUCCESS"
        assert run_record["records_fetched"] == 0


# ── show_stats ───────────────────────────────────────────────────


class TestShowStats:
    @patch("src.battlefield.db_helpers.get_critical_gates")
    @patch("src.battlefield.db_helpers.get_dashboard_stats")
    def test_prints_stats(self, mock_stats, mock_gates, capsys):
        mock_stats.return_value = {
            "total_vehicles": 10,
            "by_type": {"bill": 5, "hearing": 5},
            "by_posture": {"tracking": 8, "action_required": 2},
            "upcoming_gates_14d": 3,
            "alerts_48h": 1,
            "unacknowledged_alerts": 0,
        }
        mock_gates.return_value = [
            {"date": "2024-02-01", "title": "VA Budget Hearing gate approaching deadline"}
        ]

        run_battlefield.show_stats()

        output = capsys.readouterr().out
        assert "BATTLEFIELD DASHBOARD STATUS" in output
        assert "VEHICLES: 10" in output
        assert "GATES (next 14 days): 3" in output

    @patch("src.battlefield.db_helpers.get_critical_gates")
    @patch("src.battlefield.db_helpers.get_dashboard_stats")
    def test_no_gates(self, mock_stats, mock_gates, capsys):
        mock_stats.return_value = {
            "total_vehicles": 0,
            "by_type": {},
            "by_posture": {},
            "upcoming_gates_14d": 0,
            "alerts_48h": 0,
            "unacknowledged_alerts": 0,
        }
        mock_gates.return_value = []

        run_battlefield.show_stats()

        output = capsys.readouterr().out
        assert "VEHICLES: 0" in output


# ── init_tables ──────────────────────────────────────────────────


class TestInitTables:
    @patch("src.battlefield.db_helpers.init_battlefield_tables")
    def test_calls_init(self, mock_init):
        run_battlefield.init_tables()
        mock_init.assert_called_once()


# ── main (argument parsing) ──────────────────────────────────────


class TestMainArgParsing:
    @patch.object(run_battlefield, "show_stats")
    @patch.object(run_battlefield, "run_detection")
    @patch.object(run_battlefield, "run_sync")
    @patch.object(run_battlefield, "init_tables")
    def test_init_flag(self, mock_init, mock_sync, mock_detect, mock_stats):
        with patch("sys.argv", ["prog", "--init"]):
            run_battlefield.main()
        mock_init.assert_called_once()
        mock_sync.assert_not_called()
        mock_detect.assert_not_called()

    @patch.object(run_battlefield, "show_stats")
    @patch.object(run_battlefield, "run_detection")
    @patch.object(run_battlefield, "run_sync")
    @patch.object(run_battlefield, "init_tables")
    def test_sync_flag(self, mock_init, mock_sync, mock_detect, mock_stats):
        with patch("sys.argv", ["prog", "--sync"]):
            run_battlefield.main()
        mock_sync.assert_called_once()
        mock_detect.assert_not_called()
        mock_init.assert_not_called()

    @patch.object(run_battlefield, "show_stats")
    @patch.object(run_battlefield, "run_detection")
    @patch.object(run_battlefield, "run_sync")
    @patch.object(run_battlefield, "init_tables")
    def test_detect_flag(self, mock_init, mock_sync, mock_detect, mock_stats):
        with patch("sys.argv", ["prog", "--detect"]):
            run_battlefield.main()
        mock_detect.assert_called_once()
        mock_sync.assert_not_called()

    @patch.object(run_battlefield, "show_stats")
    @patch.object(run_battlefield, "run_detection")
    @patch.object(run_battlefield, "run_sync")
    @patch.object(run_battlefield, "init_tables")
    def test_all_flag(self, mock_init, mock_sync, mock_detect, mock_stats):
        with patch("sys.argv", ["prog", "--all"]):
            run_battlefield.main()
        mock_sync.assert_called_once()
        mock_detect.assert_called_once()

    @patch.object(run_battlefield, "show_stats")
    @patch.object(run_battlefield, "run_detection")
    @patch.object(run_battlefield, "run_sync")
    @patch.object(run_battlefield, "init_tables")
    def test_stats_flag(self, mock_init, mock_sync, mock_detect, mock_stats):
        with patch("sys.argv", ["prog", "--stats"]):
            run_battlefield.main()
        mock_stats.assert_called_once()
        mock_sync.assert_not_called()

    @patch.object(run_battlefield, "show_stats")
    @patch.object(run_battlefield, "run_detection")
    @patch.object(run_battlefield, "run_sync")
    @patch.object(run_battlefield, "init_tables")
    def test_no_args_shows_help(self, mock_init, mock_sync, mock_detect, mock_stats):
        with patch("sys.argv", ["prog"]):
            with pytest.raises(SystemExit) as exc_info:
                run_battlefield.main()
            assert exc_info.value.code == 0


import pytest
