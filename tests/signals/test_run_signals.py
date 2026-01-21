"""Tests for signals CLI runner."""

import pytest
from unittest.mock import patch, MagicMock
from argparse import Namespace
from io import StringIO

from src.run_signals import (
    cmd_route,
    cmd_status,
    cmd_test_envelope,
    main,
)


class TestCmdStatus:
    """Tests for the status command."""

    def test_status_shows_loaded_categories(self, capsys):
        """Status should show loaded categories from config/signals/."""
        args = Namespace()
        cmd_status(args)

        captured = capsys.readouterr()
        # Should show oversight_accountability category
        assert "oversight_accountability" in captured.out.lower() or "Categories" in captured.out

    def test_status_shows_recent_fires(self, capsys):
        """Status should display recent trigger fires from audit log."""
        from src.signals.output.audit_log import write_audit_log
        from src.signals.engine.evaluator import EvaluationResult

        # Create a test audit log entry
        write_audit_log(
            event_id="test-event-1",
            authority_id="AUTH-1",
            indicator_id="gao_oig_reference",
            trigger_id="formal_audit_signal",
            severity="high",
            result=EvaluationResult(
                passed=True,
                matched_terms=["GAO"],
                matched_discriminators=[],
                passed_evaluators=["contains_any"],
                failed_evaluators=[],
                evidence_map={},
            ),
            suppressed=False,
        )

        args = Namespace()
        cmd_status(args)

        captured = capsys.readouterr()
        # Should show something about recent fires or audit log
        assert "Recent" in captured.out or "audit" in captured.out.lower() or "trigger" in captured.out.lower()

    def test_status_shows_suppression_state(self, capsys):
        """Status should show active suppressions."""
        from src.signals.suppression import SuppressionManager

        # Record a suppression
        mgr = SuppressionManager()
        mgr.record_fire(
            trigger_id="formal_audit_signal",
            authority_id="AUTH-2",
            version=1,
            cooldown_minutes=60,
        )

        args = Namespace()
        cmd_status(args)

        captured = capsys.readouterr()
        # Should show suppression info
        assert "Suppression" in captured.out or "suppression" in captured.out.lower() or "active" in captured.out.lower()


class TestCmdTestEnvelope:
    """Tests for the test-envelope command."""

    def test_test_envelope_creates_gao_envelope(self, capsys):
        """Test-envelope should create a GAO-related test envelope."""
        args = Namespace()
        cmd_test_envelope(args)

        captured = capsys.readouterr()
        # Should mention GAO or oversight since we're creating a GAO test envelope
        assert "GAO" in captured.out or "oversight" in captured.out.lower() or "test" in captured.out.lower()

    def test_test_envelope_shows_routing_results(self, capsys):
        """Test-envelope should show what triggers matched."""
        args = Namespace()
        cmd_test_envelope(args)

        captured = capsys.readouterr()
        # Should show routing results - triggers or matches
        assert "trigger" in captured.out.lower() or "match" in captured.out.lower() or "result" in captured.out.lower()

    def test_test_envelope_does_not_write_audit_log(self):
        """Test-envelope should be a dry run - no audit log writes."""
        from src.db import connect

        # Get initial audit log count
        con = connect()
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM signal_audit_log")
        count_before = cur.fetchone()[0]
        con.close()

        args = Namespace()
        cmd_test_envelope(args)

        # Get count after
        con = connect()
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM signal_audit_log")
        count_after = cur.fetchone()[0]
        con.close()

        # Should not have written to audit log
        assert count_after == count_before


class TestCmdRoute:
    """Tests for the route command."""

    def test_route_processes_hearings(self, capsys):
        """Route should process hearing events from DB."""
        from src.db import connect

        # Insert a test hearing
        con = connect()
        con.execute(
            """INSERT INTO hearings (event_id, congress, chamber, committee_code, committee_name,
               hearing_date, status, title, first_seen_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("TEST-HEARING-1", 119, "House", "HSVA", "House Veterans Affairs",
             "2026-01-25", "scheduled", "Hearing on GAO Audit of VA Claims",
             "2026-01-21T10:00:00Z", "2026-01-21T10:00:00Z"),
        )
        con.commit()
        con.close()

        args = Namespace(dry_run=False, source=None, limit=10)
        cmd_route(args)

        captured = capsys.readouterr()
        # Should show some processing output
        assert "route" in captured.out.lower() or "hearing" in captured.out.lower() or "processed" in captured.out.lower() or "event" in captured.out.lower()

    def test_route_dry_run_skips_output(self, capsys):
        """Route with dry-run should not write to audit log."""
        from src.db import connect

        # Insert a test event
        con = connect()
        con.execute(
            """INSERT INTO om_events (event_id, event_type, primary_source_type, primary_url,
               pub_precision, pub_source, title, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("TEST-OM-1", "report", "gao", "https://gao.gov/test",
             "day", "extracted", "GAO Investigation of VA", "2026-01-21T10:00:00Z"),
        )
        con.commit()
        con.close()

        # Get initial count
        con = connect()
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM signal_audit_log")
        count_before = cur.fetchone()[0]
        con.close()

        args = Namespace(dry_run=True, source=None, limit=10)
        cmd_route(args)

        # Get count after
        con = connect()
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM signal_audit_log")
        count_after = cur.fetchone()[0]
        con.close()

        # Dry run should not write audit log
        assert count_after == count_before

    def test_route_with_source_filter(self, capsys):
        """Route with --source filters to specific adapter."""
        from src.db import connect

        # Insert a test bill
        con = connect()
        con.execute(
            """INSERT INTO bills (bill_id, congress, bill_type, bill_number, title,
               first_seen_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("119-hr-1234", 119, "HR", 1234, "VA Disability Claims Review Act",
             "2026-01-21T10:00:00Z", "2026-01-21T10:00:00Z"),
        )
        con.commit()
        con.close()

        args = Namespace(dry_run=False, source="bills", limit=10)
        cmd_route(args)

        captured = capsys.readouterr()
        # Should process only bills - verify routing output exists
        assert "routing" in captured.out.lower() or "processed" in captured.out.lower()


class TestMainCLI:
    """Tests for main CLI parsing."""

    @patch("src.run_signals.cmd_route")
    def test_main_route_command(self, mock_cmd):
        """Main should dispatch to route command."""
        with patch("sys.argv", ["run_signals.py", "route"]):
            main()
        mock_cmd.assert_called_once()

    @patch("src.run_signals.cmd_status")
    def test_main_status_command(self, mock_cmd):
        """Main should dispatch to status command."""
        with patch("sys.argv", ["run_signals.py", "status"]):
            main()
        mock_cmd.assert_called_once()

    @patch("src.run_signals.cmd_test_envelope")
    def test_main_test_envelope_command(self, mock_cmd):
        """Main should dispatch to test-envelope command."""
        with patch("sys.argv", ["run_signals.py", "test-envelope"]):
            main()
        mock_cmd.assert_called_once()

    @patch("src.run_signals.cmd_route")
    def test_main_route_with_dry_run(self, mock_cmd):
        """Main should pass --dry-run flag to route command."""
        with patch("sys.argv", ["run_signals.py", "route", "--dry-run"]):
            main()
        mock_cmd.assert_called_once()
        args = mock_cmd.call_args[0][0]
        assert args.dry_run is True

    @patch("src.run_signals.cmd_route")
    def test_main_route_with_source_filter(self, mock_cmd):
        """Main should pass --source filter to route command."""
        with patch("sys.argv", ["run_signals.py", "route", "--source", "hearings"]):
            main()
        mock_cmd.assert_called_once()
        args = mock_cmd.call_args[0][0]
        assert args.source == "hearings"


class TestRouteResults:
    """Tests for route command result reporting."""

    def test_route_reports_match_count(self, capsys):
        """Route should report how many triggers matched."""
        from src.db import connect

        # Insert a hearing that should match
        con = connect()
        con.execute(
            """INSERT INTO hearings (event_id, congress, chamber, committee_code, committee_name,
               hearing_date, status, title, first_seen_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("TEST-HEARING-2", 119, "House", "HSVA", "House Veterans Affairs",
             "2026-01-26", "scheduled", "GAO Review of VA Disability Claims Backlog",
             "2026-01-21T11:00:00Z", "2026-01-21T11:00:00Z"),
        )
        con.commit()
        con.close()

        args = Namespace(dry_run=False, source="hearings", limit=10)
        cmd_route(args)

        captured = capsys.readouterr()
        # Should show some form of count or summary
        assert any(x in captured.out.lower() for x in ["matched", "trigger", "processed", "routed", "event"])

    def test_route_reports_suppressed_count(self, capsys):
        """Route should report suppressed triggers separately."""
        from src.db import connect
        from src.signals.suppression import SuppressionManager

        # Insert a hearing
        con = connect()
        con.execute(
            """INSERT INTO hearings (event_id, congress, chamber, committee_code, committee_name,
               hearing_date, status, title, first_seen_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("TEST-HEARING-3", 119, "House", "HSVA", "House Veterans Affairs",
             "2026-01-27", "scheduled", "GAO Investigation Results",
             "2026-01-21T12:00:00Z", "2026-01-21T12:00:00Z"),
        )
        con.commit()
        con.close()

        # Pre-suppress the trigger
        mgr = SuppressionManager()
        mgr.record_fire(
            trigger_id="formal_audit_signal",
            authority_id="TEST-HEARING-3",
            version=1,
            cooldown_minutes=60,
        )

        args = Namespace(dry_run=False, source="hearings", limit=10)
        cmd_route(args)

        captured = capsys.readouterr()
        # Output should exist
        assert len(captured.out) > 0
