"""Tests for aggregate health score engine."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from src.db import connect, execute
from src.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
)
from src.resilience.health_score import (
    _compute_circuit_breaker_health,
    _compute_data_coverage,
    _compute_error_rate,
    _compute_freshness,
    _score_to_grade,
    compute_health_score,
)
from src.resilience.staleness_monitor import SourceExpectation


def _insert_run(source_id: str, status: str, minutes_ago: int = 5):
    """Insert a source_run with given status ending N minutes ago."""
    con = connect()
    now = datetime.now(UTC)
    ended = (now - timedelta(minutes=minutes_ago)).isoformat()
    started = (now - timedelta(minutes=minutes_ago + 1)).isoformat()
    execute(
        con,
        """INSERT INTO source_runs(source_id, started_at, ended_at, status, records_fetched, errors_json)
           VALUES (:sid, :started, :ended, :status, 10, '[]')""",
        {"sid": source_id, "started": started, "ended": ended, "status": status},
    )
    con.commit()
    con.close()


def _insert_fr_record(minutes_ago: int = 5):
    """Insert a fr_seen record to test data coverage."""
    con = connect()
    now = datetime.now(UTC)
    ts = (now - timedelta(minutes=minutes_ago)).isoformat()
    execute(
        con,
        """INSERT INTO fr_seen(doc_id, published_date, first_seen_at, source_url)
           VALUES (:doc_id, :pub_date, :ts, :url)""",
        {"doc_id": f"FR-{minutes_ago}", "pub_date": ts[:10], "ts": ts, "url": "http://test"},
    )
    con.commit()
    con.close()


class TestScoreToGrade:
    def test_grade_a(self):
        assert _score_to_grade(95) == "A"
        assert _score_to_grade(90) == "A"

    def test_grade_b(self):
        assert _score_to_grade(80) == "B"
        assert _score_to_grade(75) == "B"

    def test_grade_c(self):
        assert _score_to_grade(65) == "C"
        assert _score_to_grade(60) == "C"

    def test_grade_d(self):
        assert _score_to_grade(45) == "D"
        assert _score_to_grade(40) == "D"

    def test_grade_f(self):
        assert _score_to_grade(30) == "F"
        assert _score_to_grade(0) == "F"
        assert _score_to_grade(39.9) == "F"


class TestComputeFreshness:
    def test_no_expectations_returns_100(self):
        """No configured expectations -> score 100."""
        with patch("src.resilience.health_score.load_expectations", return_value=[]):
            con = connect()
            try:
                result = _compute_freshness(con)
            finally:
                con.close()
        assert result.score == 100.0
        assert result.weight == 0.35

    def test_all_sources_fresh(self):
        """All sources with recent SUCCESS -> score ~100."""
        expectations = [
            SourceExpectation("federal_register", "daily", 6, 24, True),
            SourceExpectation("bills_congress", "daily", 12, 48, False),
        ]
        _insert_run("federal_register", "SUCCESS", minutes_ago=5)
        _insert_run("bills_congress", "SUCCESS", minutes_ago=5)

        with patch("src.resilience.health_score.load_expectations", return_value=expectations):
            con = connect()
            try:
                result = _compute_freshness(con)
            finally:
                con.close()
        assert result.score == 100.0

    def test_critical_source_down_degrades_more(self):
        """Missing critical source (2x weight) degrades score more than non-critical."""
        expectations = [
            SourceExpectation("federal_register", "daily", 6, 24, True),
            SourceExpectation("bills_congress", "daily", 12, 48, False),
        ]
        # Only bills_congress has data, critical FR missing
        _insert_run("bills_congress", "SUCCESS", minutes_ago=5)

        with patch("src.resilience.health_score.load_expectations", return_value=expectations):
            con = connect()
            try:
                result = _compute_freshness(con)
            finally:
                con.close()
        # Weight: FR=2 (critical, missing), bills=1 (fresh). Fresh=1/3=33.3%
        assert result.score < 50


class TestComputeErrorRate:
    def test_all_success_returns_100(self):
        """All SUCCESS runs -> 100 score."""
        expectations = [
            SourceExpectation("federal_register", "daily", 6, 24, True),
        ]
        _insert_run("federal_register", "SUCCESS", minutes_ago=5)
        _insert_run("federal_register", "SUCCESS", minutes_ago=60)

        with patch("src.resilience.health_score.load_expectations", return_value=expectations):
            con = connect()
            try:
                result = _compute_error_rate(con)
            finally:
                con.close()
        assert result.score == 100.0
        assert result.weight == 0.30

    def test_high_failure_rate_applies_penalty(self):
        """Source with >50% failure rate gets -20 penalty."""
        expectations = [
            SourceExpectation("federal_register", "daily", 6, 24, True),
        ]
        # 3 errors, 1 success = 75% failure rate
        _insert_run("federal_register", "ERROR", minutes_ago=5)
        _insert_run("federal_register", "ERROR", minutes_ago=10)
        _insert_run("federal_register", "ERROR", minutes_ago=15)
        _insert_run("federal_register", "SUCCESS", minutes_ago=20)

        with patch("src.resilience.health_score.load_expectations", return_value=expectations):
            con = connect()
            try:
                result = _compute_error_rate(con)
            finally:
                con.close()
        # Base: 1/4 = 25%, minus 20 penalty = 5
        assert result.score <= 10
        assert result.details["high_failure_sources"] == ["federal_register"]

    def test_no_runs_returns_100(self):
        """No runs at all -> score 100 (no evidence of failure)."""
        expectations = [
            SourceExpectation("nonexistent", "daily", 6, 24, False),
        ]
        with patch("src.resilience.health_score.load_expectations", return_value=expectations):
            con = connect()
            try:
                result = _compute_error_rate(con)
            finally:
                con.close()
        assert result.score == 100.0

    def test_no_data_not_counted_as_failure(self):
        """NO_DATA is a normal outcome and should NOT penalize health score."""
        expectations = [
            SourceExpectation("federal_register", "daily", 6, 24, True),
        ]
        # All NO_DATA runs — source checked, nothing new each time
        _insert_run("federal_register", "NO_DATA", minutes_ago=5)
        _insert_run("federal_register", "NO_DATA", minutes_ago=60)
        _insert_run("federal_register", "NO_DATA", minutes_ago=120)

        with patch("src.resilience.health_score.load_expectations", return_value=expectations):
            con = connect()
            try:
                result = _compute_error_rate(con)
            finally:
                con.close()
        assert result.score == 100.0
        assert result.details["high_failure_sources"] == []

    def test_mixed_no_data_and_error(self):
        """Only ERROR counts as failure; NO_DATA and SUCCESS are healthy."""
        expectations = [
            SourceExpectation("federal_register", "daily", 6, 24, True),
        ]
        # 2 NO_DATA + 1 SUCCESS + 1 ERROR = 1/4 failure rate = 25%
        _insert_run("federal_register", "NO_DATA", minutes_ago=5)
        _insert_run("federal_register", "NO_DATA", minutes_ago=10)
        _insert_run("federal_register", "SUCCESS", minutes_ago=15)
        _insert_run("federal_register", "ERROR", minutes_ago=20)

        with patch("src.resilience.health_score.load_expectations", return_value=expectations):
            con = connect()
            try:
                result = _compute_error_rate(con)
            finally:
                con.close()
        # Base: 3/4 success = 75%, no penalty (failure rate 25% < 50%)
        assert result.score == 75.0
        assert result.details["high_failure_sources"] == []


class TestComputeCircuitBreakerHealth:
    def test_all_closed_returns_100(self):
        """All CBs CLOSED -> 100."""
        result = _compute_circuit_breaker_health()
        # All pre-configured CBs are CLOSED (reset by conftest)
        assert result.score == 100.0
        assert result.weight == 0.20

    def test_open_cb_degrades_score(self):
        """OPEN CB reduces score proportionally."""
        cb = CircuitBreaker("test_health_open", CircuitBreakerConfig())
        cb._state = CircuitState.OPEN

        result = _compute_circuit_breaker_health()
        assert result.score < 100.0
        assert result.details["states"]["open"] >= 1

    def test_half_open_cb_half_weight(self):
        """HALF_OPEN contributes half value."""
        cb = CircuitBreaker("test_health_half", CircuitBreakerConfig())
        cb._state = CircuitState.HALF_OPEN

        result = _compute_circuit_breaker_health()
        assert result.score < 100.0
        assert result.details["states"]["half_open"] >= 1


class TestComputeDataCoverage:
    def test_missing_table_reduces_coverage(self):
        """Tables that don't exist reduce coverage."""
        con = connect()
        try:
            result = _compute_data_coverage(con)
        finally:
            con.close()
        # source_runs table exists (from conftest), others may or may not
        assert result.weight == 0.15
        assert 0 <= result.score <= 100

    def test_active_table_increases_coverage(self):
        """Table with recent data counts as active."""
        _insert_fr_record(minutes_ago=5)
        _insert_run("test_source", "SUCCESS", minutes_ago=5)

        con = connect()
        try:
            result = _compute_data_coverage(con)
        finally:
            con.close()
        assert result.details["tables"]["source_runs"] != "no_recent_data"
        assert result.details["tables"]["fr_seen"] != "no_recent_data"


class TestComputeHealthScore:
    def test_healthy_system_scores_high(self):
        """System with recent data, no errors, all CBs closed -> high score."""
        expectations = [
            SourceExpectation("federal_register", "daily", 6, 24, True),
        ]
        _insert_run("federal_register", "SUCCESS", minutes_ago=5)
        _insert_fr_record(minutes_ago=5)

        with patch("src.resilience.health_score.load_expectations", return_value=expectations):
            result = compute_health_score()

        assert result.score >= 60
        assert result.grade in ("A", "B", "C")
        assert result.computed_at is not None
        assert len(result.dimensions) == 4

    def test_degraded_system_scores_lower(self):
        """System with errors and open CBs -> lower score."""
        expectations = [
            SourceExpectation("federal_register", "daily", 6, 24, True),
        ]
        _insert_run("federal_register", "ERROR", minutes_ago=5)
        _insert_run("federal_register", "ERROR", minutes_ago=10)
        _insert_run("federal_register", "ERROR", minutes_ago=15)

        # Open some circuit breakers
        cb1 = CircuitBreaker("test_hs_1", CircuitBreakerConfig())
        cb2 = CircuitBreaker("test_hs_2", CircuitBreakerConfig())
        cb3 = CircuitBreaker("test_hs_3", CircuitBreakerConfig())
        cb1._state = CircuitState.OPEN
        cb2._state = CircuitState.OPEN
        cb3._state = CircuitState.OPEN

        with patch("src.resilience.health_score.load_expectations", return_value=expectations):
            result = compute_health_score()

        assert result.score < 80
        # Should have incidents from the CB cascade
        assert len(result.incidents) > 0

    def test_aggregate_health_has_correct_structure(self):
        """AggregateHealth has all required fields."""
        with patch("src.resilience.health_score.load_expectations", return_value=[]):
            result = compute_health_score()

        assert hasattr(result, "score")
        assert hasattr(result, "grade")
        assert hasattr(result, "dimensions")
        assert hasattr(result, "incidents")
        assert hasattr(result, "computed_at")
        assert isinstance(result.dimensions, list)
        assert isinstance(result.incidents, list)
        dim_names = {d.name for d in result.dimensions}
        assert dim_names == {
            "source_freshness",
            "error_rate",
            "circuit_breaker_health",
            "data_coverage",
        }
