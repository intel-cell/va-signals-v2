"""Tests for src/run_oversight.py — CLI runner for Oversight Monitor."""

import argparse
from unittest.mock import MagicMock, patch

from src import run_oversight

# ── Argument parsing ─────────────────────────────────────────────


class TestMainArgParsing:
    def test_run_command_default(self):
        """When no command given, defaults to run with agent=None."""
        with patch.object(run_oversight, "cmd_run") as mock_run:
            with patch("sys.argv", ["prog"]):
                run_oversight.main()
            args = mock_run.call_args[0][0]
            assert args.agent is None
            assert args.since is None

    def test_run_with_agent(self):
        with patch.object(run_oversight, "cmd_run") as mock_run:
            with patch("sys.argv", ["prog", "run", "--agent", "gao"]):
                run_oversight.main()
            args = mock_run.call_args[0][0]
            assert args.agent == "gao"

    def test_backfill_command(self):
        with patch.object(run_oversight, "cmd_backfill") as mock_bf:
            with patch(
                "sys.argv",
                [
                    "prog",
                    "backfill",
                    "--agent",
                    "gao",
                    "--start",
                    "2025-01-01",
                    "--end",
                    "2025-06-01",
                ],
            ):
                run_oversight.main()
            args = mock_bf.call_args[0][0]
            assert args.agent == "gao"
            assert args.start == "2025-01-01"
            assert args.end == "2025-06-01"

    def test_digest_command(self):
        with patch.object(run_oversight, "cmd_digest") as mock_d:
            with patch(
                "sys.argv", ["prog", "digest", "--start", "2026-01-13", "--end", "2026-01-20"]
            ):
                run_oversight.main()
            args = mock_d.call_args[0][0]
            assert args.start == "2026-01-13"
            assert args.output is None

    def test_digest_with_output(self):
        with patch.object(run_oversight, "cmd_digest") as mock_d:
            with patch(
                "sys.argv",
                ["prog", "digest", "--start", "2026-01-13", "--end", "2026-01-20", "-o", "out.md"],
            ):
                run_oversight.main()
            args = mock_d.call_args[0][0]
            assert args.output == "out.md"

    def test_baseline_command(self):
        with patch.object(run_oversight, "cmd_baseline") as mock_bl:
            with patch("sys.argv", ["prog", "baseline"]):
                run_oversight.main()
            args = mock_bl.call_args[0][0]
            assert args.window_days == 90
            assert args.source is None

    def test_baseline_with_source(self):
        with patch.object(run_oversight, "cmd_baseline") as mock_bl:
            with patch("sys.argv", ["prog", "baseline", "--source", "gao", "--window-days", "60"]):
                run_oversight.main()
            args = mock_bl.call_args[0][0]
            assert args.source == "gao"
            assert args.window_days == 60

    def test_status_command(self):
        with patch.object(run_oversight, "cmd_status") as mock_st:
            with patch("sys.argv", ["prog", "status"]):
                run_oversight.main()
            mock_st.assert_called_once()


# ── cmd_run ──────────────────────────────────────────────────────


class TestCmdRun:
    @patch.object(run_oversight, "init_oversight")
    @patch.object(run_oversight, "init_db")
    @patch.object(run_oversight, "run_all_agents")
    def test_run_all_agents(self, mock_run_all, mock_init_db, mock_init_ov, capsys):
        result = MagicMock(
            agent="gao",
            status="SUCCESS",
            events_fetched=5,
            events_processed=3,
            escalations=1,
            errors=[],
        )
        mock_run_all.return_value = [result]

        args = argparse.Namespace(agent=None, since=None)
        run_oversight.cmd_run(args)

        mock_init_db.assert_called_once()
        mock_init_ov.assert_called_once()
        mock_run_all.assert_called_once_with(since=None)
        output = capsys.readouterr().out
        assert "Oversight Monitor Run Complete" in output

    @patch.object(run_oversight, "init_oversight")
    @patch.object(run_oversight, "init_db")
    @patch.object(run_oversight, "run_agent")
    def test_run_single_agent(self, mock_run, mock_init_db, mock_init_ov, capsys):
        mock_run.return_value = MagicMock(
            agent="gao",
            status="SUCCESS",
            events_fetched=10,
            events_processed=8,
            escalations=2,
            errors=[],
        )

        args = argparse.Namespace(agent="gao", since=None)
        run_oversight.cmd_run(args)

        mock_run.assert_called_once_with("gao", since=None)
        output = capsys.readouterr().out
        assert "gao" in output
        assert "Fetched: 10" in output

    @patch.object(run_oversight, "init_oversight")
    @patch.object(run_oversight, "init_db")
    @patch.object(run_oversight, "run_agent")
    def test_run_single_agent_with_errors(self, mock_run, mock_init_db, mock_init_ov, capsys):
        mock_run.return_value = MagicMock(
            agent="gao",
            status="ERROR",
            events_fetched=0,
            events_processed=0,
            escalations=0,
            errors=["API timeout"],
        )

        args = argparse.Namespace(agent="gao", since=None)
        run_oversight.cmd_run(args)

        output = capsys.readouterr().out
        assert "Errors:" in output

    @patch.object(run_oversight, "init_oversight")
    @patch.object(run_oversight, "init_db")
    @patch.object(run_oversight, "run_agent")
    def test_run_with_since(self, mock_run, mock_init_db, mock_init_ov):
        mock_run.return_value = MagicMock(
            agent="gao",
            status="SUCCESS",
            events_fetched=0,
            events_processed=0,
            escalations=0,
            errors=[],
        )
        args = argparse.Namespace(agent="gao", since="2026-01-01T00:00:00")
        run_oversight.cmd_run(args)
        call_kwargs = mock_run.call_args
        assert call_kwargs[1]["since"] is not None


# ── cmd_backfill ─────────────────────────────────────────────────


class TestCmdBackfill:
    @patch.object(run_oversight, "init_oversight")
    @patch.object(run_oversight, "init_db")
    @patch.object(run_oversight, "run_backfill")
    def test_backfill(self, mock_bf, mock_init_db, mock_init_ov, capsys):
        mock_bf.return_value = MagicMock(
            status="SUCCESS",
            events_fetched=50,
            events_processed=48,
        )
        args = argparse.Namespace(agent="gao", start="2025-01-01", end="2025-06-01")
        run_oversight.cmd_backfill(args)

        mock_bf.assert_called_once_with(
            agent_name="gao", start_date="2025-01-01", end_date="2025-06-01"
        )
        output = capsys.readouterr().out
        assert "Backfill gao" in output


# ── cmd_digest ───────────────────────────────────────────────────


class TestCmdDigest:
    @patch.object(run_oversight, "init_db")
    @patch.object(run_oversight, "generate_digest")
    def test_digest_to_stdout(self, mock_gen, mock_init_db, capsys):
        mock_gen.return_value = "## Weekly Digest\n- Item 1"
        args = argparse.Namespace(start="2026-01-13", end="2026-01-20", output=None)
        run_oversight.cmd_digest(args)
        output = capsys.readouterr().out
        assert "Weekly Digest" in output

    @patch.object(run_oversight, "init_db")
    @patch.object(run_oversight, "generate_digest")
    def test_digest_to_file(self, mock_gen, mock_init_db, tmp_path, capsys):
        mock_gen.return_value = "## Digest"
        out_file = tmp_path / "digest.md"
        args = argparse.Namespace(start="2026-01-13", end="2026-01-20", output=str(out_file))
        run_oversight.cmd_digest(args)
        assert out_file.read_text() == "## Digest"
        output = capsys.readouterr().out
        assert "Digest written to" in output


# ── cmd_baseline ─────────────────────────────────────────────────


class TestCmdBaseline:
    @patch.object(run_oversight, "init_db")
    def test_baseline_single_source(self, mock_init_db, capsys):
        mock_baseline = MagicMock(
            source_type="gao",
            event_count=42,
            window_start="2025-10-01",
            window_end="2026-01-01",
            summary="42 events",
            topic_distribution={"oversight": 0.5, "budget": 0.3},
        )
        with patch("src.oversight.pipeline.baseline.build_baseline", return_value=mock_baseline):
            args = argparse.Namespace(source="gao", window_days=90)
            run_oversight.cmd_baseline(args)
        output = capsys.readouterr().out
        assert "gao" in output
        assert "42 events" in output

    @patch.object(run_oversight, "init_db")
    def test_baseline_no_events(self, mock_init_db, capsys):
        with patch("src.oversight.pipeline.baseline.build_baseline", return_value=None):
            args = argparse.Namespace(source="gao", window_days=90)
            run_oversight.cmd_baseline(args)
        output = capsys.readouterr().out
        assert "no events" in output

    @patch.object(run_oversight, "init_db")
    def test_baseline_all_sources(self, mock_init_db, capsys):
        bl = MagicMock(
            source_type="gao",
            event_count=10,
            window_start="2025-10-01",
            window_end="2026-01-01",
            topic_distribution=None,
        )
        with patch("src.oversight.pipeline.baseline.build_all_baselines", return_value=[bl]):
            args = argparse.Namespace(source=None, window_days=90)
            run_oversight.cmd_baseline(args)
        output = capsys.readouterr().out
        assert "Baseline Computation Complete" in output

    @patch.object(run_oversight, "init_db")
    def test_baseline_all_empty(self, mock_init_db, capsys):
        with patch("src.oversight.pipeline.baseline.build_all_baselines", return_value=[]):
            args = argparse.Namespace(source=None, window_days=90)
            run_oversight.cmd_baseline(args)
        output = capsys.readouterr().out
        assert "no events found" in output


# ── cmd_status ───────────────────────────────────────────────────


class TestCmdStatus:
    @patch.object(run_oversight, "init_db")
    def test_status_output(self, mock_init_db, capsys):
        # Set up an in-memory db with the om_events table
        import src.db as db_module

        con = db_module.connect()

        # Insert a test event so status has data
        db_module.execute(
            con,
            """
            INSERT INTO om_events(event_id, event_type, primary_source_type, primary_url,
                pub_timestamp, pub_precision, pub_source, title, fetched_at, is_escalation)
            VALUES('E1', 'report', 'gao', 'https://gao.gov/1', '2026-01-15', 'day', 'gao', 'Test Report', '2026-01-15', 0)
        """,
        )
        con.commit()
        con.close()

        with patch.dict(run_oversight.AGENT_REGISTRY, {"gao": object(), "crs": object()}):
            args = argparse.Namespace()
            run_oversight.cmd_status(args)

        output = capsys.readouterr().out
        assert "Oversight Monitor Status" in output
        assert "Total events:" in output
        assert "gao" in output
