"""Test that post_run_check persists staleness alerts to the DB."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from src.db import connect, execute
from src.resilience.run_lifecycle import RunContext, post_run_check
from src.resilience.staleness_monitor import SourceExpectation


def _seed_old_run(source_id: str, hours_ago: float):
    """Insert a source_run that ended `hours_ago` hours in the past."""
    con = connect()
    ended_at = (datetime.now(UTC) - timedelta(hours=hours_ago)).isoformat()
    started_at = (datetime.now(UTC) - timedelta(hours=hours_ago + 0.1)).isoformat()
    execute(
        con,
        """
        INSERT INTO source_runs (source_id, started_at, ended_at, status, records_fetched, errors_json)
        VALUES (:source_id, :started_at, :ended_at, 'SUCCESS', 1, '[]')
        """,
        {
            "source_id": source_id,
            "started_at": started_at,
            "ended_at": ended_at,
        },
    )
    con.commit()
    con.close()


class TestPostRunCheckPersistsStalenessAlerts:
    def test_stale_source_persists_alert(self):
        """When a source is stale, post_run_check should write to staleness_alerts."""
        # Seed an old run 48 hours ago
        _seed_old_run("fr_delta", hours_ago=48)

        # Create an expectation that triggers after 24 hours
        expectation = SourceExpectation(
            source_id="fr_delta",
            frequency="daily",
            tolerance_hours=6,
            alert_after_hours=24,
            is_critical=False,
        )

        # Patch load_expectations to return our test expectation
        # and patch canary to avoid import errors
        with (
            patch(
                "src.resilience.staleness_monitor.load_expectations",
                return_value=[expectation],
            ),
            patch("src.resilience.canary.run_canaries", return_value=[]),
        ):
            ctx = RunContext(source_id="fr_delta")
            ctx = post_run_check(ctx, run_record=None)

        # Verify staleness was detected
        assert len(ctx.postcondition_failures) >= 1
        assert any("stale" in f.lower() or "fr_delta" in f for f in ctx.postcondition_failures)

        # Verify alert was persisted to DB
        con = connect()
        cur = execute(
            con,
            "SELECT source_id, severity FROM staleness_alerts WHERE source_id LIKE :pattern",
            {"pattern": "%fr_delta%"},
        )
        rows = cur.fetchall()
        con.close()

        assert len(rows) >= 1, "Expected at least 1 staleness alert in DB"
        assert rows[0][0] == "fr_delta"

    def test_healthy_source_no_alert(self):
        """When a source is fresh, no staleness alert should be persisted."""
        # Seed a recent run (1 hour ago -- well within tolerance)
        _seed_old_run("fr_delta_healthy", hours_ago=1)

        expectation = SourceExpectation(
            source_id="fr_delta_healthy",
            frequency="daily",
            tolerance_hours=6,
            alert_after_hours=24,
            is_critical=False,
        )

        with (
            patch(
                "src.resilience.staleness_monitor.load_expectations",
                return_value=[expectation],
            ),
            patch("src.resilience.canary.run_canaries", return_value=[]),
        ):
            ctx = RunContext(source_id="fr_delta_healthy")
            ctx = post_run_check(ctx, run_record=None)

        # No staleness failures
        stale_failures = [f for f in ctx.postcondition_failures if "stale" in f.lower()]
        assert len(stale_failures) == 0

        # No alert rows in DB
        con = connect()
        cur = execute(
            con,
            "SELECT COUNT(*) FROM staleness_alerts WHERE source_id LIKE :pattern",
            {"pattern": "%fr_delta_healthy%"},
        )
        count = cur.fetchone()[0]
        con.close()

        assert count == 0, "Healthy source should not produce staleness alerts"
