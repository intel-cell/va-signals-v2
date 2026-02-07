"""Pipeline canary assertions — domain knowledge encoded as runtime checks.

Each canary check encodes a heuristic about what "healthy" pipeline output
looks like.  Failures are advisory (logged as warnings), not fatal.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


@dataclass
class CanaryResult:
    """Outcome of a single canary assertion."""

    passed: bool
    message: str
    severity: str = "warning"  # "warning" or "critical"


# ---------------------------------------------------------------------------
# Individual canary checks
# ---------------------------------------------------------------------------


def weekday_has_documents(source_id: str, run_record: dict | None = None) -> CanaryResult:
    """On weekdays (Mon-Fri), FR-type sources should return > 0 documents."""
    today = datetime.now(UTC)
    if today.weekday() >= 5:  # Saturday=5, Sunday=6
        return CanaryResult(passed=True, message="Weekend — weekday doc check skipped")

    records_fetched = 0
    if run_record and isinstance(run_record, dict):
        records_fetched = run_record.get("records_fetched", 0)

    if records_fetched == 0:
        return CanaryResult(
            passed=False,
            message=f"{source_id}: 0 documents fetched on a weekday",
            severity="warning",
        )
    return CanaryResult(passed=True, message=f"{source_id}: {records_fetched} documents fetched")


def no_duplicate_ids(table: str, id_column: str) -> CanaryResult:
    """Verify no duplicate values exist in the specified column."""
    try:
        from src.db import connect, execute

        con = connect()
        cur = execute(
            con,
            f"SELECT {id_column}, COUNT(*) AS cnt FROM {table} "  # noqa: S608
            f"GROUP BY {id_column} HAVING cnt > 1 LIMIT 5",
        )
        dupes = cur.fetchall()
        con.close()

        if dupes:
            dupe_ids = [str(row[0]) for row in dupes]
            return CanaryResult(
                passed=False,
                message=f"Duplicate {id_column} in {table}: {', '.join(dupe_ids)}",
                severity="critical",
            )
        return CanaryResult(passed=True, message=f"No duplicate {id_column} in {table}")
    except Exception as e:
        return CanaryResult(
            passed=False,
            message=f"Failed to check duplicates in {table}.{id_column}: {e}",
            severity="warning",
        )


def timestamps_monotonic(table: str, ts_column: str) -> CanaryResult:
    """Verify that the last 10 rows have non-decreasing timestamps."""
    try:
        from src.db import connect, execute

        con = connect()
        cur = execute(
            con,
            f"SELECT {ts_column} FROM {table} "  # noqa: S608
            f"ORDER BY rowid DESC LIMIT 10",
        )
        rows = cur.fetchall()
        con.close()

        if len(rows) < 2:
            return CanaryResult(passed=True, message=f"Not enough rows in {table} to check")

        # Rows come in DESC order from DB; reverse to get chronological
        timestamps = [row[0] for row in reversed(rows) if row[0] is not None]

        for i in range(1, len(timestamps)):
            if timestamps[i] < timestamps[i - 1]:
                return CanaryResult(
                    passed=False,
                    message=(
                        f"Non-monotonic {ts_column} in {table}: "
                        f"{timestamps[i - 1]} > {timestamps[i]}"
                    ),
                    severity="warning",
                )
        return CanaryResult(passed=True, message=f"Timestamps monotonic in {table}.{ts_column}")
    except Exception as e:
        return CanaryResult(
            passed=False,
            message=f"Failed to check timestamps in {table}.{ts_column}: {e}",
            severity="warning",
        )


# ---------------------------------------------------------------------------
# Canary registry — maps source_id → list of check callables
# ---------------------------------------------------------------------------

# Each entry is a callable(source_id, run_record) -> CanaryResult
CanaryCheck = Callable[[str, dict | None], CanaryResult]


def _wrap_table_check(
    fn: Callable[..., CanaryResult], *args: str
) -> Callable[[str, dict | None], CanaryResult]:
    """Wrap a table-level check so it conforms to the (source_id, run_record) signature."""

    def _check(_source_id: str, _run_record: dict | None = None) -> CanaryResult:
        return fn(*args)

    return _check


CANARY_REGISTRY: dict[str, list[CanaryCheck]] = {
    "govinfo_fr_bulk": [
        weekday_has_documents,
        _wrap_table_check(no_duplicate_ids, "fr_seen", "doc_id"),
        _wrap_table_check(timestamps_monotonic, "source_runs", "ended_at"),
    ],
    "ecfr_delta": [
        _wrap_table_check(no_duplicate_ids, "ecfr_seen", "doc_id"),
        _wrap_table_check(timestamps_monotonic, "source_runs", "ended_at"),
    ],
    "congress_bills": [
        _wrap_table_check(no_duplicate_ids, "bills", "bill_id"),
        _wrap_table_check(timestamps_monotonic, "source_runs", "ended_at"),
    ],
    "congress_hearings": [
        _wrap_table_check(no_duplicate_ids, "hearings", "event_id"),
        _wrap_table_check(timestamps_monotonic, "source_runs", "ended_at"),
    ],
    "oversight": [
        _wrap_table_check(no_duplicate_ids, "om_events", "event_id"),
        _wrap_table_check(timestamps_monotonic, "source_runs", "ended_at"),
    ],
    "lda_gov": [
        _wrap_table_check(no_duplicate_ids, "lda_filings", "filing_uuid"),
        _wrap_table_check(timestamps_monotonic, "source_runs", "ended_at"),
    ],
    "authority_aggregate": [
        _wrap_table_check(timestamps_monotonic, "source_runs", "ended_at"),
    ],
    "battlefield_sync": [
        _wrap_table_check(timestamps_monotonic, "source_runs", "ended_at"),
    ],
    "signals_routing": [
        _wrap_table_check(timestamps_monotonic, "source_runs", "ended_at"),
    ],
}


def run_canaries(source_id: str, run_record: dict | None = None) -> list[CanaryResult]:
    """Run all registered canary checks for *source_id*.

    Returns a (possibly empty) list of :class:`CanaryResult` objects.
    """
    checks = CANARY_REGISTRY.get(source_id, [])
    results: list[CanaryResult] = []
    for check in checks:
        try:
            results.append(check(source_id, run_record))
        except Exception as e:
            results.append(
                CanaryResult(
                    passed=False,
                    message=f"Canary check raised: {e}",
                    severity="warning",
                )
            )
    return results
