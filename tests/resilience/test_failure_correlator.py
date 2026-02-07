"""Tests for failure correlation engine."""

from datetime import UTC, datetime, timedelta

from src.db import connect, execute
from src.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
)
from src.resilience.failure_correlator import (
    detect_circuit_breaker_cascade,
    detect_correlated_failures,
    get_current_incident,
    get_recent_incidents,
)


def _insert_error_run(source_id: str, minutes_ago: int = 5):
    """Insert an ERROR source_run ending N minutes ago."""
    con = connect()
    now = datetime.now(UTC)
    ended = (now - timedelta(minutes=minutes_ago)).isoformat()
    started = (now - timedelta(minutes=minutes_ago + 1)).isoformat()
    execute(
        con,
        """INSERT INTO source_runs(source_id, started_at, ended_at, status, records_fetched, errors_json)
           VALUES (:sid, :started, :ended, 'ERROR', 0, '[]')""",
        {"sid": source_id, "started": started, "ended": ended},
    )
    con.commit()
    con.close()


def _insert_success_run(source_id: str, minutes_ago: int = 5):
    """Insert a SUCCESS source_run ending N minutes ago."""
    con = connect()
    now = datetime.now(UTC)
    ended = (now - timedelta(minutes=minutes_ago)).isoformat()
    started = (now - timedelta(minutes=minutes_ago + 1)).isoformat()
    execute(
        con,
        """INSERT INTO source_runs(source_id, started_at, ended_at, status, records_fetched, errors_json)
           VALUES (:sid, :started, :ended, 'SUCCESS', 10, '[]')""",
        {"sid": source_id, "started": started, "ended": ended},
    )
    con.commit()
    con.close()


class TestDetectCorrelatedFailures:
    def test_no_errors_returns_none(self):
        """No ERROR runs in window -> None."""
        result = detect_correlated_failures(window_minutes=30)
        assert result is None

    def test_single_source_error_returns_isolated(self):
        """1 source with errors -> isolated incident."""
        _insert_error_run("federal_register", minutes_ago=5)
        result = detect_correlated_failures(window_minutes=30)
        assert result is not None
        assert result.incident_type == "isolated"
        assert result.affected_sources == ["federal_register"]
        assert result.error_count == 1

    def test_two_sources_returns_source_cluster(self):
        """2 sources with errors -> source_cluster."""
        _insert_error_run("federal_register", minutes_ago=5)
        _insert_error_run("bills_congress", minutes_ago=5)
        result = detect_correlated_failures(window_minutes=30)
        assert result is not None
        assert result.incident_type == "source_cluster"
        assert len(result.affected_sources) == 2

    def test_three_sources_returns_infrastructure(self):
        """3+ sources with errors -> infrastructure incident."""
        _insert_error_run("federal_register", minutes_ago=5)
        _insert_error_run("bills_congress", minutes_ago=5)
        _insert_error_run("oversight", minutes_ago=5)
        result = detect_correlated_failures(window_minutes=30, min_sources=3)
        assert result is not None
        assert result.incident_type == "infrastructure"
        assert len(result.affected_sources) == 3
        assert result.error_count == 3

    def test_errors_outside_window_ignored(self):
        """Errors older than the window are not counted."""
        _insert_error_run("federal_register", minutes_ago=60)
        result = detect_correlated_failures(window_minutes=30)
        assert result is None

    def test_multiple_errors_same_source(self):
        """Multiple errors from one source still classified as isolated."""
        _insert_error_run("federal_register", minutes_ago=5)
        _insert_error_run("federal_register", minutes_ago=10)
        _insert_error_run("federal_register", minutes_ago=15)
        result = detect_correlated_failures(window_minutes=30)
        assert result is not None
        assert result.incident_type == "isolated"
        assert result.error_count == 3


class TestDetectCircuitBreakerCascade:
    def test_no_open_breakers_returns_none(self):
        """All CBs CLOSED -> None."""
        result = detect_circuit_breaker_cascade()
        assert result is None

    def test_three_open_breakers_returns_cascade(self):
        """3+ OPEN CBs -> cascade incident."""
        cb1 = CircuitBreaker("test_cascade_1", CircuitBreakerConfig(failure_threshold=1))
        cb2 = CircuitBreaker("test_cascade_2", CircuitBreakerConfig(failure_threshold=1))
        cb3 = CircuitBreaker("test_cascade_3", CircuitBreakerConfig(failure_threshold=1))
        cb1._state = CircuitState.OPEN
        cb2._state = CircuitState.OPEN
        cb3._state = CircuitState.OPEN

        result = detect_circuit_breaker_cascade(min_open=3)
        assert result is not None
        assert result.incident_type == "infrastructure"
        assert result.is_cascade is True
        assert len(result.affected_sources) == 3

    def test_two_open_breakers_below_threshold(self):
        """2 OPEN CBs with min_open=3 -> None."""
        cb1 = CircuitBreaker("test_two_1", CircuitBreakerConfig(failure_threshold=1))
        cb2 = CircuitBreaker("test_two_2", CircuitBreakerConfig(failure_threshold=1))
        cb1._state = CircuitState.OPEN
        cb2._state = CircuitState.OPEN

        result = detect_circuit_breaker_cascade(min_open=3)
        assert result is None


class TestGetRecentIncidents:
    def test_no_issues_returns_empty(self):
        """No errors, no open CBs -> empty list."""
        incidents = get_recent_incidents(hours=24)
        assert incidents == []

    def test_includes_failure_and_cascade(self):
        """Returns both correlated failures and CB cascades."""
        _insert_error_run("source_a", minutes_ago=5)

        cb1 = CircuitBreaker("test_ri_1", CircuitBreakerConfig(failure_threshold=1))
        cb2 = CircuitBreaker("test_ri_2", CircuitBreakerConfig(failure_threshold=1))
        cb3 = CircuitBreaker("test_ri_3", CircuitBreakerConfig(failure_threshold=1))
        cb1._state = CircuitState.OPEN
        cb2._state = CircuitState.OPEN
        cb3._state = CircuitState.OPEN

        incidents = get_recent_incidents(hours=24)
        assert len(incidents) == 2
        types = {i.incident_type for i in incidents}
        assert "isolated" in types or "infrastructure" in types


class TestGetCurrentIncident:
    def test_no_issues_returns_none(self):
        """No current issues -> None."""
        result = get_current_incident()
        assert result is None

    def test_cascade_preferred_over_isolated(self):
        """CB cascade returned instead of isolated failure."""
        _insert_error_run("source_x", minutes_ago=5)

        cb1 = CircuitBreaker("test_cur_1", CircuitBreakerConfig(failure_threshold=1))
        cb2 = CircuitBreaker("test_cur_2", CircuitBreakerConfig(failure_threshold=1))
        cb3 = CircuitBreaker("test_cur_3", CircuitBreakerConfig(failure_threshold=1))
        cb1._state = CircuitState.OPEN
        cb2._state = CircuitState.OPEN
        cb3._state = CircuitState.OPEN

        result = get_current_incident()
        assert result is not None
        assert result.is_cascade is True
