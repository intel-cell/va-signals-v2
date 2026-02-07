"""Tests for src.resilience.run_lifecycle module."""

from unittest.mock import MagicMock, patch

from src.resilience.run_lifecycle import (
    RunContext,
    post_run_check,
    pre_run_check,
    with_lifecycle,
)


class TestPreRunCheck:
    """Tests for pre_run_check()."""

    def test_db_unreachable_fails_precondition(self):
        """Pre-run check should fail when DB is unreachable."""
        with patch("src.db.connect", side_effect=RuntimeError("DB connection failed")):
            ctx = pre_run_check("govinfo_fr_bulk")

        assert ctx.preconditions_passed is False
        assert ctx.source_id == "govinfo_fr_bulk"

    def test_db_unreachable_returns_failed_context(self):
        """Pre-run should set preconditions_passed=False when DB raises."""
        with patch("src.db.connect", side_effect=Exception("cannot connect")):
            ctx = pre_run_check("govinfo_fr_bulk")
        assert ctx.preconditions_passed is False

    def test_circuit_breaker_open_fails_precondition(self):
        """Pre-run should fail when circuit breaker is OPEN."""
        from src.resilience.circuit_breaker import CircuitState

        mock_cb = MagicMock()
        mock_cb.state = CircuitState.OPEN

        mock_con = MagicMock()

        with (
            patch("src.db.connect", return_value=mock_con),
            patch(
                "src.resilience.circuit_breaker.CircuitBreaker.get",
                return_value=mock_cb,
            ),
        ):
            ctx = pre_run_check("govinfo_fr_bulk")

        assert ctx.preconditions_passed is False

    def test_healthy_state_passes(self):
        """Pre-run should pass when DB is up and no CB is open."""
        mock_con = MagicMock()

        with (
            patch("src.db.connect", return_value=mock_con),
            patch(
                "src.resilience.circuit_breaker.CircuitBreaker.get",
                return_value=None,
            ),
        ):
            ctx = pre_run_check("govinfo_fr_bulk")

        assert ctx.preconditions_passed is True
        assert ctx.source_id == "govinfo_fr_bulk"


class TestPostRunCheck:
    """Tests for post_run_check()."""

    def test_calls_canaries_and_checks_staleness(self):
        """Post-run should invoke canary checks and staleness monitor."""
        ctx = RunContext(source_id="govinfo_fr_bulk")

        mock_canary_result = MagicMock()
        mock_canary_result.passed = True
        mock_canary_result.message = "OK"

        with (
            patch(
                "src.resilience.canary.run_canaries",
                return_value=[mock_canary_result],
            ),
            patch(
                "src.resilience.staleness_monitor.load_expectations",
                return_value=[],
            ),
        ):
            ctx = post_run_check(ctx, run_record=None)

        assert ctx.canary_failures == []
        assert ctx.postcondition_failures == []

    def test_records_canary_failures(self):
        """Post-run should record canary failures."""
        ctx = RunContext(source_id="govinfo_fr_bulk")

        mock_canary_result = MagicMock()
        mock_canary_result.passed = False
        mock_canary_result.message = "0 documents on weekday"
        mock_canary_result.severity = "warning"

        with (
            patch(
                "src.resilience.canary.run_canaries",
                return_value=[mock_canary_result],
            ),
            patch(
                "src.resilience.staleness_monitor.load_expectations",
                return_value=[],
            ),
        ):
            ctx = post_run_check(ctx, run_record=None)

        assert len(ctx.canary_failures) == 1
        assert "0 documents on weekday" in ctx.canary_failures[0]


class TestWithLifecycleDecorator:
    """Tests for @with_lifecycle decorator."""

    def test_preserves_return_value(self):
        """Decorator should preserve the wrapped function's return value."""
        expected = {"source_id": "test", "status": "SUCCESS"}

        @with_lifecycle("govinfo_fr_bulk")
        def fake_runner():
            return expected

        mock_con = MagicMock()

        with (
            patch("src.db.connect", return_value=mock_con),
            patch(
                "src.resilience.circuit_breaker.CircuitBreaker.get",
                return_value=None,
            ),
            patch("src.resilience.canary.run_canaries", return_value=[]),
            patch(
                "src.resilience.staleness_monitor.load_expectations",
                return_value=[],
            ),
        ):
            result = fake_runner()

        assert result == expected

    def test_returns_none_when_preconditions_fail(self):
        """Decorator should return None if preconditions fail."""

        @with_lifecycle("govinfo_fr_bulk")
        def fake_runner():
            return {"status": "SUCCESS"}

        with patch("src.db.connect", side_effect=Exception("DB down")):
            result = fake_runner()

        assert result is None

    def test_preserves_function_name(self):
        """Decorator should preserve __name__ via functools.wraps."""

        @with_lifecycle("govinfo_fr_bulk")
        def my_special_runner():
            return {}

        assert my_special_runner.__name__ == "my_special_runner"

    def test_passes_args_and_kwargs(self):
        """Decorator should pass through positional and keyword arguments."""

        @with_lifecycle("govinfo_fr_bulk")
        def runner_with_args(a, b, flag=False):
            return {"a": a, "b": b, "flag": flag}

        mock_con = MagicMock()

        with (
            patch("src.db.connect", return_value=mock_con),
            patch(
                "src.resilience.circuit_breaker.CircuitBreaker.get",
                return_value=None,
            ),
            patch("src.resilience.canary.run_canaries", return_value=[]),
            patch(
                "src.resilience.staleness_monitor.load_expectations",
                return_value=[],
            ),
        ):
            result = runner_with_args(1, 2, flag=True)

        assert result == {"a": 1, "b": 2, "flag": True}
