"""Standardized run lifecycle framework with pre/post hooks.

Wraps pipeline runner functions with precondition checks (DB reachable,
circuit breaker state) and postcondition checks (run record verification,
canary assertions, staleness).
"""

import functools
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

APPROVED_SOURCES = [
    "govinfo_fr_bulk",
    "govinfo_ecfr_title_38",
    "ecfr_delta",
    "congress_bills",
    "congress_hearings",
    "oversight",
    "lda_gov",
    "authority_aggregate",
    "battlefield_sync",
    "battlefield_detection",
    "agenda_drift",
    "signals_routing",
]


@dataclass
class RunContext:
    """Context object passed through pre/post lifecycle hooks."""

    source_id: str
    preconditions_passed: bool = True
    postcondition_failures: list[str] = field(default_factory=list)
    canary_failures: list[str] = field(default_factory=list)


def pre_run_check(source_id: str) -> RunContext:
    """Verify preconditions before pipeline run."""
    ctx = RunContext(source_id=source_id)

    # Check 1: DB reachable
    try:
        from src.db import connect

        con = connect()
        con.execute("SELECT 1")
        con.close()
    except Exception as e:
        logger.error(
            "PRE_RUN_FAILED: DB unreachable",
            extra={"source_id": source_id, "error": str(e)},
        )
        ctx.preconditions_passed = False
        return ctx

    # Check 2: Circuit breaker not OPEN for this source
    try:
        from src.resilience.circuit_breaker import CircuitBreaker, CircuitState

        cb = CircuitBreaker.get(source_id)
        if cb and cb.state == CircuitState.OPEN:
            logger.warning(
                "PRE_RUN_WARNING: Circuit breaker OPEN",
                extra={"source_id": source_id},
            )
            ctx.preconditions_passed = False
            return ctx
    except Exception:
        pass  # CB may not exist for all sources

    # Check 3: Source in approved list (warn only, don't block)
    if source_id not in APPROVED_SOURCES:
        logger.warning(
            "PRE_RUN_WARNING: Unknown source_id",
            extra={"source_id": source_id},
        )

    return ctx


def post_run_check(ctx: RunContext, run_record: dict | None = None) -> RunContext:
    """Verify postconditions after pipeline run."""

    # Check 1: If run_record provided with a row ID, verify it landed in DB
    if run_record and run_record.get("run_id"):
        try:
            from src.db import connect, execute

            con = connect()
            cur = execute(
                con,
                "SELECT id FROM source_runs WHERE id = :row_id",
                {"row_id": run_record["run_id"]},
            )
            if not cur.fetchone():
                ctx.postcondition_failures.append(
                    f"source_run {run_record['run_id']} not found in DB"
                )
                logger.error(
                    "POST_RUN_VERIFY_FAILED",
                    extra={"run_id": run_record["run_id"]},
                )
            con.close()
        except Exception as e:
            ctx.postcondition_failures.append(f"DB verification failed: {e}")

    # Check 2: Run canary assertions
    try:
        from src.resilience.canary import run_canaries

        canary_results = run_canaries(ctx.source_id, run_record)
        for result in canary_results:
            if not result.passed:
                ctx.canary_failures.append(result.message)
                logger.warning(
                    "CANARY_FAILED",
                    extra={
                        "source_id": ctx.source_id,
                        "check": result.message,
                        "severity": result.severity,
                    },
                )
    except ImportError:
        pass  # canary module may not exist yet
    except Exception as e:
        logger.warning(
            "CANARY_ERROR",
            extra={"source_id": ctx.source_id, "error": str(e)},
        )

    # Check 3: Check staleness via staleness_monitor
    try:
        from src.resilience.staleness_monitor import check_source, load_expectations, persist_alert

        expectations = load_expectations()
        for exp in expectations:
            if exp.source_id in ctx.source_id or ctx.source_id in exp.source_id:
                alert = check_source(exp)
                if alert is not None:
                    ctx.postcondition_failures.append(
                        f"Source {ctx.source_id} stale: {alert.message}"
                    )
                    logger.warning(
                        "POST_RUN_STALE",
                        extra={"source_id": ctx.source_id, "severity": alert.severity},
                    )
                    persist_alert(alert)
                break
    except Exception:
        pass  # staleness monitor may not have this source configured

    return ctx


def with_lifecycle(source_id: str) -> Callable:
    """Decorator that wraps runner functions with pre/post lifecycle hooks.

    Usage::

        @with_lifecycle("govinfo_fr_bulk")
        def run_fr_delta(max_months: int = 3) -> dict:
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Pre-run checks
            ctx = pre_run_check(source_id)
            if not ctx.preconditions_passed:
                logger.error(
                    "LIFECYCLE_PRECONDITION_FAILED",
                    extra={"source_id": source_id},
                )
                return None

            # Execute the wrapped runner
            result = func(*args, **kwargs)

            # Build run_record hint for post-check verification
            run_record = None
            if isinstance(result, dict) and "run_id" in result:
                run_record = result

            # Post-run checks
            ctx = post_run_check(ctx, run_record)

            if ctx.postcondition_failures:
                logger.warning(
                    "LIFECYCLE_POSTCONDITION_FAILURES",
                    extra={
                        "source_id": source_id,
                        "failures": ctx.postcondition_failures,
                    },
                )
            if ctx.canary_failures:
                logger.warning(
                    "LIFECYCLE_CANARY_FAILURES",
                    extra={
                        "source_id": source_id,
                        "failures": ctx.canary_failures,
                    },
                )

            return result

        return wrapper

    return decorator
