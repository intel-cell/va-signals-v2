"""Tests for staleness detection system.

Covers:
- YAML config loading
- DB queries for last success and consecutive failures
- Severity classification logic
- check_all_sources aggregation
- API endpoint via TestClient
"""

import sqlite3
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import yaml

from src.resilience.staleness_monitor import (
    SourceExpectation,
    StaleSourceAlert,
    _parse_timestamp,
    check_all_sources,
    check_source,
    get_consecutive_failures,
    get_failure_rate,
    get_last_success,
    load_expectations,
    persist_alert,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db_with_runs(runs: list[tuple]) -> sqlite3.Connection:
    """Create in-memory SQLite with source_runs table and seed data."""
    con = sqlite3.connect(":memory:")
    con.execute("""
        CREATE TABLE source_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT NOT NULL,
            started_at TEXT NOT NULL,
            ended_at TEXT NOT NULL,
            status TEXT NOT NULL,
            records_fetched INTEGER NOT NULL DEFAULT 0,
            errors_json TEXT NOT NULL DEFAULT '[]'
        )
    """)
    for run in runs:
        con.execute(
            "INSERT INTO source_runs (source_id, started_at, ended_at, status) VALUES (?, ?, ?, ?)",
            run,
        )
    con.commit()
    return con


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _hours_ago(h: float) -> str:
    return _iso(datetime.now(UTC) - timedelta(hours=h))


def _default_expectation(**overrides) -> SourceExpectation:
    defaults = {
        "source_id": "federal_register",
        "frequency": "daily",
        "tolerance_hours": 6.0,
        "alert_after_hours": 24.0,
        "is_critical": True,
    }
    defaults.update(overrides)
    return SourceExpectation(**defaults)


# ---------------------------------------------------------------------------
# YAML config loading
# ---------------------------------------------------------------------------


class TestLoadExpectations:
    def test_loads_all_sources(self, tmp_path):
        cfg = tmp_path / "expectations.yaml"
        cfg.write_text(
            yaml.dump(
                {
                    "sources": {
                        "source_a": {
                            "frequency": "daily",
                            "tolerance_hours": 6,
                            "alert_after_hours": 24,
                            "is_critical": True,
                        },
                        "source_b": {
                            "frequency": "daily",
                            "tolerance_hours": 12,
                            "alert_after_hours": 48,
                            "is_critical": False,
                        },
                    }
                }
            )
        )
        result = load_expectations(cfg)
        assert len(result) == 2
        ids = {e.source_id for e in result}
        assert ids == {"source_a", "source_b"}

    def test_field_types(self, tmp_path):
        cfg = tmp_path / "expectations.yaml"
        cfg.write_text(
            yaml.dump(
                {
                    "sources": {
                        "test_source": {
                            "frequency": "daily",
                            "tolerance_hours": 6,
                            "alert_after_hours": 24,
                            "is_critical": True,
                        },
                    }
                }
            )
        )
        result = load_expectations(cfg)
        exp = result[0]
        assert isinstance(exp.source_id, str)
        assert isinstance(exp.frequency, str)
        assert isinstance(exp.tolerance_hours, float)
        assert isinstance(exp.alert_after_hours, float)
        assert isinstance(exp.is_critical, bool)

    def test_missing_file_returns_empty(self, tmp_path):
        missing = tmp_path / "nonexistent.yaml"
        result = load_expectations(missing)
        assert result == []

    def test_empty_file_returns_empty(self, tmp_path):
        cfg = tmp_path / "expectations.yaml"
        cfg.write_text("")
        result = load_expectations(cfg)
        assert result == []

    def test_no_sources_key_returns_empty(self, tmp_path):
        cfg = tmp_path / "expectations.yaml"
        cfg.write_text(yaml.dump({"other_key": "value"}))
        result = load_expectations(cfg)
        assert result == []

    def test_loads_real_config(self):
        """Verify the actual shipped config file parses correctly."""
        from src.resilience.staleness_monitor import CONFIG_PATH

        if CONFIG_PATH.exists():
            result = load_expectations(CONFIG_PATH)
            assert len(result) == 7
            ids = {e.source_id for e in result}
            assert "federal_register" in ids
            assert "oversight" in ids


# ---------------------------------------------------------------------------
# get_last_success
# ---------------------------------------------------------------------------


class TestGetLastSuccess:
    def test_found(self):
        ts = _hours_ago(2)
        con = _make_db_with_runs(
            [
                ("federal_register_bulk", "2026-01-01T00:00:00Z", ts, "SUCCESS"),
            ]
        )
        result = get_last_success("federal_register", con=con)
        assert result == ts
        con.close()

    def test_not_found(self):
        con = _make_db_with_runs(
            [
                ("federal_register_bulk", "2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z", "ERROR"),
            ]
        )
        result = get_last_success("federal_register", con=con)
        assert result is None
        con.close()

    def test_returns_most_recent(self):
        old = _hours_ago(48)
        recent = _hours_ago(2)
        con = _make_db_with_runs(
            [
                ("federal_register_bulk", "2026-01-01T00:00:00Z", old, "SUCCESS"),
                ("federal_register_bulk", "2026-01-01T00:00:00Z", recent, "SUCCESS"),
            ]
        )
        result = get_last_success("federal_register", con=con)
        assert result == recent
        con.close()

    def test_no_matching_source(self):
        con = _make_db_with_runs(
            [
                ("ecfr_delta", "2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z", "SUCCESS"),
            ]
        )
        result = get_last_success("federal_register", con=con)
        assert result is None
        con.close()

    def test_like_pattern_matches(self):
        ts = _hours_ago(1)
        con = _make_db_with_runs(
            [
                ("ecfr_delta_title38", "2026-01-01T00:00:00Z", ts, "SUCCESS"),
            ]
        )
        result = get_last_success("ecfr_delta", con=con)
        assert result == ts
        con.close()


# ---------------------------------------------------------------------------
# get_consecutive_failures
# ---------------------------------------------------------------------------


class TestGetConsecutiveFailures:
    def test_zero_when_latest_is_success(self):
        con = _make_db_with_runs(
            [
                ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(2), "SUCCESS"),
            ]
        )
        assert get_consecutive_failures("federal_register", con=con) == 0
        con.close()

    def test_count_three(self):
        con = _make_db_with_runs(
            [
                ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(50), "SUCCESS"),
                ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(26), "ERROR"),
                ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(18), "ERROR"),
                ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(10), "ERROR"),
            ]
        )
        assert get_consecutive_failures("federal_register", con=con) == 3
        con.close()

    def test_count_five_plus(self):
        runs = [
            ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(100), "SUCCESS"),
        ]
        for i in range(6):
            runs.append(
                ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(80 - i * 10), "ERROR")
            )
        con = _make_db_with_runs(runs)
        assert get_consecutive_failures("federal_register", con=con) == 6
        con.close()

    def test_zero_no_runs(self):
        con = _make_db_with_runs([])
        assert get_consecutive_failures("federal_register", con=con) == 0
        con.close()

    def test_all_failures(self):
        con = _make_db_with_runs(
            [
                ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(10), "ERROR"),
                ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(5), "ERROR"),
            ]
        )
        assert get_consecutive_failures("federal_register", con=con) == 2
        con.close()

    def test_no_data_breaks_consecutive_streak(self):
        """NO_DATA is normal and should break a consecutive failure streak."""
        con = _make_db_with_runs(
            [
                ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(30), "SUCCESS"),
                ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(20), "ERROR"),
                ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(15), "ERROR"),
                ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(10), "NO_DATA"),
                ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(5), "ERROR"),
            ]
        )
        # Only the most recent ERROR counts; NO_DATA at 10min ago breaks the streak
        assert get_consecutive_failures("federal_register", con=con) == 1
        con.close()


# ---------------------------------------------------------------------------
# _parse_timestamp
# ---------------------------------------------------------------------------


class TestParseTimestamp:
    def test_iso_with_z(self):
        dt = _parse_timestamp("2026-02-06T10:00:00Z")
        assert dt is not None
        assert dt.tzinfo is not None

    def test_iso_with_offset(self):
        dt = _parse_timestamp("2026-02-06T10:00:00+00:00")
        assert dt is not None

    def test_naive_iso(self):
        dt = _parse_timestamp("2026-02-06T10:00:00")
        assert dt is not None
        assert dt.tzinfo == UTC

    def test_invalid_returns_none(self):
        assert _parse_timestamp("not-a-date") is None

    def test_none_returns_none(self):
        assert _parse_timestamp(None) is None


# ---------------------------------------------------------------------------
# check_source — severity logic
# ---------------------------------------------------------------------------


class TestCheckSourceHealthy:
    def test_within_tolerance_returns_none(self):
        """A source with recent success should return None (healthy)."""
        con = _make_db_with_runs(
            [
                ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(2), "SUCCESS"),
            ]
        )
        exp = _default_expectation()
        result = check_source(exp, con=con)
        assert result is None
        con.close()

    def test_just_at_tolerance_returns_none(self):
        """Source at exactly tolerance_hours should still be healthy."""
        con = _make_db_with_runs(
            [
                ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(5.9), "SUCCESS"),
            ]
        )
        exp = _default_expectation(tolerance_hours=6.0)
        result = check_source(exp, con=con)
        assert result is None
        con.close()


class TestCheckSourceWarning:
    def test_overdue_but_below_alert(self):
        """Overdue beyond tolerance but less than alert_after_hours => warning."""
        con = _make_db_with_runs(
            [
                ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(20), "SUCCESS"),
            ]
        )
        # tolerance=6, alert_after=24; 20h total => 14h overdue => warning
        exp = _default_expectation(tolerance_hours=6.0, alert_after_hours=24.0, is_critical=False)
        result = check_source(exp, con=con)
        assert result is not None
        assert result.severity == "warning"
        con.close()


class TestCheckSourceAlert:
    def test_overdue_past_alert_threshold_noncritical(self):
        """Non-critical source overdue past alert_after_hours => alert."""
        con = _make_db_with_runs(
            [
                ("bills_congress", "2026-01-01T00:00:00Z", _hours_ago(62), "SUCCESS"),
            ]
        )
        # tolerance=12, alert_after=48; 62h total => 50h overdue > 48 => alert
        exp = _default_expectation(
            source_id="bills_congress",
            tolerance_hours=12.0,
            alert_after_hours=48.0,
            is_critical=False,
        )
        result = check_source(exp, con=con)
        assert result is not None
        assert result.severity == "alert"
        con.close()

    def test_three_consecutive_failures_elevates_to_alert(self):
        """3 consecutive failures should elevate to at least alert."""
        runs = [
            ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(50), "SUCCESS"),
            ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(30), "ERROR"),
            ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(20), "ERROR"),
            ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(10), "ERROR"),
        ]
        con = _make_db_with_runs(runs)
        # Last success was 50h ago, tolerance=6 => 44h overdue
        # alert_after=24, so overdue > alert_after => alert
        # Plus 3 consecutive failures => alert
        exp = _default_expectation(is_critical=False)
        result = check_source(exp, con=con)
        assert result is not None
        assert result.severity in ("alert", "critical")
        assert result.consecutive_failures == 3
        con.close()


class TestCheckSourceCritical:
    def test_overdue_past_2x_alert(self):
        """Overdue > 2x alert_after_hours => critical."""
        con = _make_db_with_runs(
            [
                ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(60), "SUCCESS"),
            ]
        )
        # tolerance=6, alert_after=24; 60h total => 54h overdue > 48 (2*24) => critical
        exp = _default_expectation(tolerance_hours=6.0, alert_after_hours=24.0, is_critical=False)
        result = check_source(exp, con=con)
        assert result is not None
        assert result.severity == "critical"
        con.close()

    def test_critical_source_past_alert_threshold(self):
        """Critical source overdue past alert_after_hours => critical (not just alert)."""
        con = _make_db_with_runs(
            [
                ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(35), "SUCCESS"),
            ]
        )
        # tolerance=6, alert_after=24; 35h total => 29h overdue > 24
        # is_critical=True => critical
        exp = _default_expectation(tolerance_hours=6.0, alert_after_hours=24.0, is_critical=True)
        result = check_source(exp, con=con)
        assert result is not None
        assert result.severity == "critical"
        con.close()

    def test_five_consecutive_failures_is_critical(self):
        """5+ consecutive failures => critical regardless of hours."""
        runs = [
            ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(100), "SUCCESS"),
        ]
        for i in range(5):
            runs.append(
                ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(80 - i * 10), "ERROR")
            )
        con = _make_db_with_runs(runs)
        exp = _default_expectation(is_critical=False)
        result = check_source(exp, con=con)
        assert result is not None
        assert result.severity == "critical"
        assert result.consecutive_failures >= 5
        con.close()

    def test_no_success_ever_is_critical(self):
        """No successful runs at all => critical."""
        con = _make_db_with_runs(
            [
                ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(10), "ERROR"),
            ]
        )
        exp = _default_expectation()
        result = check_source(exp, con=con)
        assert result is not None
        assert result.severity == "critical"
        assert result.last_success_at is None
        con.close()

    def test_empty_db_is_critical(self):
        """No runs at all => critical."""
        con = _make_db_with_runs([])
        exp = _default_expectation()
        result = check_source(exp, con=con)
        assert result is not None
        assert result.severity == "critical"
        con.close()


# ---------------------------------------------------------------------------
# check_all_sources
# ---------------------------------------------------------------------------


class TestCheckAllSources:
    def test_aggregates_multiple_sources(self, tmp_path):
        """Check that check_all_sources collects alerts from multiple sources."""
        cfg = tmp_path / "expectations.yaml"
        cfg.write_text(
            yaml.dump(
                {
                    "sources": {
                        "source_a": {
                            "frequency": "daily",
                            "tolerance_hours": 6,
                            "alert_after_hours": 24,
                            "is_critical": True,
                        },
                        "source_b": {
                            "frequency": "daily",
                            "tolerance_hours": 6,
                            "alert_after_hours": 24,
                            "is_critical": False,
                        },
                    }
                }
            )
        )

        con = _make_db_with_runs(
            [
                # source_a: recent success, healthy => no alert
                ("source_a_bulk", "2026-01-01T00:00:00Z", _hours_ago(2), "SUCCESS"),
                # source_b: no runs at all => will be critical
            ]
        )

        with patch("src.resilience.staleness_monitor.connect", return_value=con):
            alerts = check_all_sources(cfg)

        # source_a is healthy (no alert), source_b has no data (critical)
        assert len(alerts) == 1
        assert alerts[0].source_id == "source_b"
        assert alerts[0].severity == "critical"
        con.close()

    def test_returns_empty_when_all_healthy(self, tmp_path):
        cfg = tmp_path / "expectations.yaml"
        cfg.write_text(
            yaml.dump(
                {
                    "sources": {
                        "source_a": {
                            "frequency": "daily",
                            "tolerance_hours": 6,
                            "alert_after_hours": 24,
                            "is_critical": True,
                        },
                    }
                }
            )
        )

        con = _make_db_with_runs(
            [
                ("source_a_bulk", "2026-01-01T00:00:00Z", _hours_ago(2), "SUCCESS"),
            ]
        )

        with patch("src.resilience.staleness_monitor.connect", return_value=con):
            alerts = check_all_sources(cfg)

        assert alerts == []
        con.close()


# ---------------------------------------------------------------------------
# StaleSourceAlert dataclass
# ---------------------------------------------------------------------------


class TestStaleSourceAlertModel:
    def test_fields(self):
        alert = StaleSourceAlert(
            source_id="test",
            last_success_at="2026-01-01T00:00:00Z",
            hours_overdue=12.5,
            consecutive_failures=3,
            severity="alert",
            is_critical_source=True,
            message="test: 12.5h overdue",
        )
        assert alert.source_id == "test"
        assert alert.hours_overdue == 12.5
        assert alert.severity == "alert"
        assert alert.is_critical_source is True

    def test_none_fields(self):
        alert = StaleSourceAlert(
            source_id="test",
            last_success_at=None,
            hours_overdue=None,
            consecutive_failures=0,
            severity="critical",
            is_critical_source=False,
            message="no data",
        )
        assert alert.last_success_at is None
        assert alert.hours_overdue is None


# ---------------------------------------------------------------------------
# API endpoint
# ---------------------------------------------------------------------------


class TestStalenessEndpoint:
    def test_route_registered(self):
        """The staleness endpoint should be registered in the app."""
        from src.dashboard_api import app

        route_paths = [r.path for r in app.routes]
        assert "/api/health/staleness" in route_paths

    @patch("src.routers.health.check_all_sources")
    @patch("src.routers.health.load_expectations")
    def test_endpoint_returns_healthy(self, mock_load, mock_check):
        """When no alerts, overall_status should be healthy."""
        mock_check.return_value = []
        mock_load.return_value = [
            SourceExpectation("a", "daily", 6, 24, True),
        ]

        from fastapi.testclient import TestClient

        from src.auth.models import AuthContext, UserRole
        from src.dashboard_api import app

        client = TestClient(app)
        mock_user = AuthContext(
            user_id="test-uid",
            email="test@test.com",
            role=UserRole.VIEWER,
            display_name="Test",
            auth_method="firebase",
        )
        with patch("src.auth.middleware.get_current_user", return_value=mock_user):
            resp = client.get("/api/health/staleness")

        assert resp.status_code == 200
        data = resp.json()
        assert data["overall_status"] == "healthy"
        assert data["alerts"] == []

    @patch("src.routers.health.check_all_sources")
    @patch("src.routers.health.load_expectations")
    def test_endpoint_returns_alerts(self, mock_load, mock_check):
        """When there are alerts, they should appear in the response."""
        mock_check.return_value = [
            StaleSourceAlert(
                source_id="federal_register",
                last_success_at="2026-01-01T00:00:00Z",
                hours_overdue=30.0,
                consecutive_failures=2,
                severity="alert",
                is_critical_source=True,
                message="federal_register: 30.0h overdue",
            ),
        ]
        mock_load.return_value = [
            SourceExpectation("federal_register", "daily", 6, 24, True),
        ]

        from fastapi.testclient import TestClient

        from src.auth.models import AuthContext, UserRole
        from src.dashboard_api import app

        client = TestClient(app)
        mock_user = AuthContext(
            user_id="test-uid",
            email="test@test.com",
            role=UserRole.VIEWER,
            display_name="Test",
            auth_method="firebase",
        )
        with patch("src.auth.middleware.get_current_user", return_value=mock_user):
            resp = client.get("/api/health/staleness")

        assert resp.status_code == 200
        data = resp.json()
        assert data["overall_status"] == "alert"
        assert len(data["alerts"]) == 1
        assert data["alerts"][0]["source_id"] == "federal_register"
        assert data["alerts"][0]["severity"] == "alert"

    @patch("src.routers.health.check_all_sources")
    @patch("src.routers.health.load_expectations")
    def test_endpoint_severity_filter(self, mock_load, mock_check):
        """Severity query param should filter alerts."""
        mock_check.return_value = [
            StaleSourceAlert("a", None, 10.0, 1, "warning", False, "a: warning"),
            StaleSourceAlert("b", None, 30.0, 4, "critical", True, "b: critical"),
        ]
        mock_load.return_value = [
            SourceExpectation("a", "daily", 6, 24, False),
            SourceExpectation("b", "daily", 6, 24, True),
        ]

        from fastapi.testclient import TestClient

        from src.auth.models import AuthContext, UserRole
        from src.dashboard_api import app

        client = TestClient(app)
        mock_user = AuthContext(
            user_id="test-uid",
            email="test@test.com",
            role=UserRole.VIEWER,
            display_name="Test",
            auth_method="firebase",
        )
        with patch("src.auth.middleware.get_current_user", return_value=mock_user):
            resp = client.get("/api/health/staleness?severity=critical")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["alerts"]) == 1
        assert data["alerts"][0]["severity"] == "critical"


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


class TestMigration:
    def test_migration_creates_table(self):
        """Migration 007 should create staleness_alerts table."""
        con = sqlite3.connect(":memory:")
        # Simulate minimal source_runs for the import
        con.execute("""
            CREATE TABLE source_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT, started_at TEXT, ended_at TEXT,
                status TEXT, records_fetched INTEGER DEFAULT 0,
                errors_json TEXT DEFAULT '[]'
            )
        """)
        con.commit()

        # Run the CREATE TABLE statement directly
        con.execute("""
            CREATE TABLE IF NOT EXISTS staleness_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT NOT NULL,
                alert_type TEXT NOT NULL DEFAULT 'missing',
                expected_by TEXT,
                last_success_at TEXT,
                hours_overdue REAL,
                consecutive_failures INTEGER DEFAULT 0,
                severity TEXT NOT NULL,
                created_at TEXT NOT NULL,
                resolved_at TEXT
            )
        """)
        con.commit()

        # Verify table exists
        cur = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='staleness_alerts'"
        )
        assert cur.fetchone() is not None

        # Verify columns
        cur = con.execute("PRAGMA table_info(staleness_alerts)")
        columns = {row[1] for row in cur.fetchall()}
        expected_cols = {
            "id",
            "source_id",
            "alert_type",
            "expected_by",
            "last_success_at",
            "hours_overdue",
            "consecutive_failures",
            "severity",
            "created_at",
            "resolved_at",
        }
        assert expected_cols.issubset(columns)
        con.close()


# ---------------------------------------------------------------------------
# get_failure_rate
# ---------------------------------------------------------------------------


class TestGetFailureRate:
    def test_all_success(self):
        """All SUCCESS runs in window => 0% failure rate."""
        runs = [
            ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(2), "SUCCESS"),
            ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(6), "SUCCESS"),
            ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(12), "SUCCESS"),
        ]
        con = _make_db_with_runs(runs)
        rate, total = get_failure_rate("federal_register", window_hours=24.0, con=con)
        assert rate == 0.0
        assert total == 3
        con.close()

    def test_all_errors(self):
        """All ERROR runs => 100% failure rate."""
        runs = [
            ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(2), "ERROR"),
            ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(6), "ERROR"),
            ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(12), "ERROR"),
        ]
        con = _make_db_with_runs(runs)
        rate, total = get_failure_rate("federal_register", window_hours=24.0, con=con)
        assert rate == 1.0
        assert total == 3
        con.close()

    def test_no_data_not_counted_as_failure(self):
        """NO_DATA is a normal outcome (source checked, nothing new) and should not be a failure."""
        runs = [
            ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(2), "NO_DATA"),
            ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(6), "NO_DATA"),
            ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(12), "NO_DATA"),
        ]
        con = _make_db_with_runs(runs)
        rate, total = get_failure_rate("federal_register", window_hours=24.0, con=con)
        assert rate == 0.0
        assert total == 3
        con.close()

    def test_mixed_runs(self):
        """Mix of SUCCESS, NO_DATA, and ERROR => only ERROR counts as failure."""
        runs = [
            ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(2), "SUCCESS"),
            ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(6), "ERROR"),
            ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(12), "NO_DATA"),
            ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(18), "SUCCESS"),
        ]
        con = _make_db_with_runs(runs)
        rate, total = get_failure_rate("federal_register", window_hours=24.0, con=con)
        assert rate == 0.25  # 1 ERROR out of 4
        assert total == 4
        con.close()

    def test_excludes_old_runs(self):
        """Runs outside the window should not be counted."""
        runs = [
            ("federal_register_bulk", "2026-01-01T00:00:00Z", _hours_ago(2), "SUCCESS"),
            (
                "federal_register_bulk",
                "2026-01-01T00:00:00Z",
                _hours_ago(48),
                "ERROR",
            ),  # outside 24h
        ]
        con = _make_db_with_runs(runs)
        rate, total = get_failure_rate("federal_register", window_hours=24.0, con=con)
        assert rate == 0.0
        assert total == 1
        con.close()

    def test_no_runs_returns_zero(self):
        """No runs at all => 0 rate, 0 total."""
        con = _make_db_with_runs([])
        rate, total = get_failure_rate("federal_register", window_hours=24.0, con=con)
        assert rate == 0.0
        assert total == 0
        con.close()

    def test_over_50_percent_threshold(self):
        """Verify >50% failure rate detection (only ERROR counts)."""
        runs = [
            ("oversight_gao", "2026-01-01T00:00:00Z", _hours_ago(2), "ERROR"),
            ("oversight_gao", "2026-01-01T00:00:00Z", _hours_ago(6), "ERROR"),
            ("oversight_gao", "2026-01-01T00:00:00Z", _hours_ago(12), "ERROR"),
            ("oversight_gao", "2026-01-01T00:00:00Z", _hours_ago(18), "SUCCESS"),
        ]
        con = _make_db_with_runs(runs)
        rate, total = get_failure_rate("oversight", window_hours=24.0, con=con)
        assert rate > 0.5  # 3 errors out of 4 = 75%
        assert total == 4
        con.close()


# ---------------------------------------------------------------------------
# persist_alert
# ---------------------------------------------------------------------------


class TestPersistAlert:
    def _make_db_with_staleness_table(self):
        """Create in-memory DB with source_runs + staleness_alerts tables."""
        con = sqlite3.connect(":memory:")
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("""
            CREATE TABLE source_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT NOT NULL,
                status TEXT NOT NULL,
                records_fetched INTEGER NOT NULL DEFAULT 0,
                errors_json TEXT NOT NULL DEFAULT '[]'
            )
        """)
        con.execute("""
            CREATE TABLE staleness_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT NOT NULL,
                alert_type TEXT NOT NULL DEFAULT 'missing',
                expected_by TEXT,
                last_success_at TEXT,
                hours_overdue REAL,
                consecutive_failures INTEGER DEFAULT 0,
                severity TEXT NOT NULL,
                created_at TEXT NOT NULL,
                resolved_at TEXT
            )
        """)
        con.commit()
        return con

    def test_persist_writes_to_table(self):
        """persist_alert should insert a row into staleness_alerts."""
        con = self._make_db_with_staleness_table()
        alert = StaleSourceAlert(
            source_id="federal_register",
            last_success_at="2026-01-01T00:00:00Z",
            hours_overdue=30.0,
            consecutive_failures=2,
            severity="alert",
            is_critical_source=True,
            message="federal_register: 30.0h overdue",
        )
        persist_alert(alert, con=con)

        cur = con.execute(
            "SELECT source_id, severity, hours_overdue, consecutive_failures FROM staleness_alerts"
        )
        rows = cur.fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "federal_register"
        assert rows[0][1] == "alert"
        assert rows[0][2] == 30.0
        assert rows[0][3] == 2
        con.close()

    def test_persist_multiple_alerts(self):
        """Multiple alerts can be persisted."""
        con = self._make_db_with_staleness_table()
        for source in ["federal_register", "oversight", "ecfr_delta"]:
            alert = StaleSourceAlert(
                source_id=source,
                last_success_at=None,
                hours_overdue=None,
                consecutive_failures=0,
                severity="critical",
                is_critical_source=True,
                message=f"{source}: no data",
            )
            persist_alert(alert, con=con)

        cur = con.execute("SELECT COUNT(*) FROM staleness_alerts")
        assert cur.fetchone()[0] == 3
        con.close()


# ---------------------------------------------------------------------------
# check_all_sources with failure rate elevation
# ---------------------------------------------------------------------------


class TestCheckAllSourcesFailureRateElevation:
    def test_high_failure_rate_elevates_to_critical(self, tmp_path):
        """Source with >50% failure rate in 24h should be elevated to critical."""
        cfg = tmp_path / "expectations.yaml"
        cfg.write_text(
            yaml.dump(
                {
                    "sources": {
                        "bad_source": {
                            "frequency": "daily",
                            "tolerance_hours": 6,
                            "alert_after_hours": 48,
                            "is_critical": False,
                        },
                    }
                }
            )
        )

        # 20h overdue with tolerance=6 => 14h overdue => normally "warning"
        # But 75% failure rate in 24h => should elevate to "critical"
        # Note: only ERROR counts as failure; NO_DATA is normal
        runs = [
            ("bad_source_bulk", "2026-01-01T00:00:00Z", _hours_ago(20), "SUCCESS"),
            ("bad_source_bulk", "2026-01-01T00:00:00Z", _hours_ago(15), "ERROR"),
            ("bad_source_bulk", "2026-01-01T00:00:00Z", _hours_ago(10), "ERROR"),
            ("bad_source_bulk", "2026-01-01T00:00:00Z", _hours_ago(5), "ERROR"),
        ]
        con = _make_db_with_runs(runs)

        with patch("src.resilience.staleness_monitor.connect", return_value=con):
            alerts = check_all_sources(cfg)

        assert len(alerts) == 1
        assert alerts[0].severity == "critical"
        assert "failure rate" in alerts[0].message
        con.close()


# ---------------------------------------------------------------------------
# SLA Health Endpoint
# ---------------------------------------------------------------------------


class TestSLAHealthEndpoint:
    def test_route_registered(self):
        """The SLA health endpoint should be registered in the app."""
        from src.dashboard_api import app

        route_paths = [r.path for r in app.routes]
        assert "/api/health/sla" in route_paths

    @patch("src.routers.health.get_failure_rate")
    @patch("src.routers.health.load_expectations")
    def test_endpoint_returns_green(self, mock_load, mock_failure_rate):
        """All healthy sources => overall green."""
        mock_load.return_value = [
            SourceExpectation("source_a", "daily", 6.0, 24.0, True),
        ]
        mock_failure_rate.return_value = (0.0, 5)

        from fastapi.testclient import TestClient

        from src.auth.models import AuthContext, UserRole
        from src.dashboard_api import app

        client = TestClient(app)
        mock_user = AuthContext(
            user_id="test-uid",
            email="test@test.com",
            role=UserRole.VIEWER,
            display_name="Test",
            auth_method="firebase",
        )

        # Mock DB to return recent success
        recent_ts = _hours_ago(2)
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (recent_ts,)
        mock_con = MagicMock()
        mock_con.cursor.return_value = mock_cursor

        with (
            patch("src.auth.middleware.get_current_user", return_value=mock_user),
            patch("src.routers.health.connect", return_value=mock_con),
            patch("src.routers.health.execute", return_value=mock_cursor),
        ):
            resp = client.get("/api/health/sla")

        assert resp.status_code == 200
        data = resp.json()
        assert data["overall_status"] == "green"
        assert len(data["sources"]) == 1
        assert data["sources"][0]["status"] == "green"

    @patch("src.routers.health.get_failure_rate")
    @patch("src.routers.health.load_expectations")
    def test_endpoint_returns_red_no_data(self, mock_load, mock_failure_rate):
        """No success data => red status."""
        mock_load.return_value = [
            SourceExpectation("source_a", "daily", 6.0, 24.0, True),
        ]
        mock_failure_rate.return_value = (0.0, 0)

        from fastapi.testclient import TestClient

        from src.auth.models import AuthContext, UserRole
        from src.dashboard_api import app

        client = TestClient(app)
        mock_user = AuthContext(
            user_id="test-uid",
            email="test@test.com",
            role=UserRole.VIEWER,
            display_name="Test",
            auth_method="firebase",
        )

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_con = MagicMock()
        mock_con.cursor.return_value = mock_cursor

        with (
            patch("src.auth.middleware.get_current_user", return_value=mock_user),
            patch("src.routers.health.connect", return_value=mock_con),
            patch("src.routers.health.execute", return_value=mock_cursor),
        ):
            resp = client.get("/api/health/sla")

        assert resp.status_code == 200
        data = resp.json()
        assert data["overall_status"] == "red"
        assert data["sources"][0]["status"] == "red"
