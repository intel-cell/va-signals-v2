"""Aggregate health score engine.

Computes a 0-100 health score across four dimensions:
- Source Freshness (35%): sources within SLA vs total
- Error Rate (30%): 24h success ratio
- Circuit Breaker Health (20%): closed vs total
- Data Coverage (15%): key tables with recent data
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from ..db import connect, execute, table_exists
from .circuit_breaker import CircuitBreaker, CircuitState
from .failure_correlator import CorrelatedIncident, get_recent_incidents
from .staleness_monitor import get_failure_rate, get_last_success, load_expectations

logger = logging.getLogger(__name__)

# Critical sources get double weight in freshness calculation
CRITICAL_SOURCES = {"federal_register", "ecfr_delta", "state_intelligence", "oversight"}

# Key tables we expect to have recent data
TRACKED_TABLES = [
    "fr_seen",
    "bills",
    "hearings",
    "om_events",
    "state_signals",
    "source_runs",
]


@dataclass
class HealthDimension:
    name: str
    score: float  # 0-100
    weight: float
    details: dict


@dataclass
class AggregateHealth:
    score: float  # 0-100 weighted
    grade: str  # A (>=90), B (>=75), C (>=60), D (>=40), F (<40)
    dimensions: list[HealthDimension]
    incidents: list[CorrelatedIncident]
    computed_at: datetime


def _score_to_grade(score: float) -> str:
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def _compute_freshness(con) -> HealthDimension:
    """Source Freshness (35%): sources within SLA / total sources.

    Critical sources (FR, ecfr, state, oversight) weighted double.
    """
    expectations = load_expectations()
    if not expectations:
        return HealthDimension(
            name="source_freshness",
            score=100.0,
            weight=0.35,
            details={"note": "no expectations configured"},
        )

    now = datetime.now(UTC)
    total_weight = 0.0
    fresh_weight = 0.0
    source_details = {}

    for exp in expectations:
        weight = 2.0 if exp.source_id in CRITICAL_SOURCES else 1.0
        total_weight += weight

        last_success = get_last_success(exp.source_id, con=con)
        if last_success is None:
            source_details[exp.source_id] = "no_data"
            continue

        try:
            ts = last_success.replace("Z", "+00:00")
            last_dt = datetime.fromisoformat(ts)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=UTC)
            hours_since = (now - last_dt).total_seconds() / 3600
        except (ValueError, TypeError):
            source_details[exp.source_id] = "parse_error"
            continue

        if hours_since <= exp.tolerance_hours:
            fresh_weight += weight
            source_details[exp.source_id] = "fresh"
        else:
            source_details[exp.source_id] = f"stale_{hours_since:.1f}h"

    score = (fresh_weight / total_weight * 100.0) if total_weight > 0 else 100.0

    return HealthDimension(
        name="source_freshness",
        score=round(score, 1),
        weight=0.35,
        details={"sources": source_details},
    )


def _compute_error_rate(con) -> HealthDimension:
    """Error Rate (30%): 24h SUCCESS count / (SUCCESS + ERROR).

    If any single source >50% failure rate, subtract 20 points.
    """
    expectations = load_expectations()
    total_success = 0
    total_runs = 0
    high_failure_sources = []
    source_rates = {}

    for exp in expectations:
        rate, runs = get_failure_rate(exp.source_id, window_hours=24.0, con=con)
        total_runs += runs
        if runs > 0:
            successes = int(runs * (1 - rate))
            total_success += successes
            source_rates[exp.source_id] = {"failure_rate": rate, "runs": runs}
            if rate > 0.5:
                high_failure_sources.append(exp.source_id)
        else:
            source_rates[exp.source_id] = {"failure_rate": 0.0, "runs": 0}

    if total_runs == 0:
        base_score = 100.0
    else:
        base_score = (total_success / total_runs) * 100.0

    # Penalty for any source with >50% failure
    penalty = 20.0 if high_failure_sources else 0.0
    score = max(0.0, base_score - penalty)

    return HealthDimension(
        name="error_rate",
        score=round(score, 1),
        weight=0.30,
        details={
            "total_runs_24h": total_runs,
            "total_success_24h": total_success,
            "high_failure_sources": high_failure_sources,
            "source_rates": source_rates,
        },
    )


def _compute_circuit_breaker_health() -> HealthDimension:
    """Circuit Breaker Health (20%): CLOSED / total CBs.

    OPEN subtracts full weight, HALF_OPEN subtracts half.
    """
    all_cbs = CircuitBreaker.all()
    total = len(all_cbs)
    if total == 0:
        return HealthDimension(
            name="circuit_breaker_health",
            score=100.0,
            weight=0.20,
            details={"total": 0},
        )

    healthy_score = 0.0
    states = {"closed": 0, "open": 0, "half_open": 0}
    for cb in all_cbs.values():
        if cb.state == CircuitState.CLOSED:
            healthy_score += 1.0
            states["closed"] += 1
        elif cb.state == CircuitState.HALF_OPEN:
            healthy_score += 0.5
            states["half_open"] += 1
        else:
            states["open"] += 1

    score = (healthy_score / total) * 100.0

    return HealthDimension(
        name="circuit_breaker_health",
        score=round(score, 1),
        weight=0.20,
        details={"total": total, "states": states},
    )


def _compute_data_coverage(con) -> HealthDimension:
    """Data Coverage (15%): key tables with data from last 24h / total tracked."""
    cutoff = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
    tables_with_data = 0
    table_status = {}

    # Map table -> timestamp column for recency check
    table_ts_columns = {
        "fr_seen": "first_seen_at",
        "bills": "last_action_date",
        "hearings": "updated_at",
        "om_events": "fetched_at",
        "state_signals": "fetched_at",
        "source_runs": "ended_at",
    }

    for tbl in TRACKED_TABLES:
        if not table_exists(con, tbl):
            table_status[tbl] = "missing"
            continue

        ts_col = table_ts_columns.get(tbl, "created_at")
        try:
            cur = execute(
                con,
                f"SELECT COUNT(*) FROM {tbl} WHERE {ts_col} >= :cutoff",
                {"cutoff": cutoff},
            )
            row = cur.fetchone()
            count = row[0] if row else 0
        except Exception:
            count = 0

        if count > 0:
            tables_with_data += 1
            table_status[tbl] = f"active ({count})"
        else:
            table_status[tbl] = "no_recent_data"

    total = len(TRACKED_TABLES)
    score = (tables_with_data / total * 100.0) if total > 0 else 100.0

    return HealthDimension(
        name="data_coverage",
        score=round(score, 1),
        weight=0.15,
        details={"tables": table_status, "active": tables_with_data, "total": total},
    )


def compute_health_score() -> AggregateHealth:
    """Compute the aggregate health score across all dimensions."""
    con = connect()
    try:
        freshness = _compute_freshness(con)
        error_rate = _compute_error_rate(con)
        cb_health = _compute_circuit_breaker_health()
        coverage = _compute_data_coverage(con)
    finally:
        con.close()

    dimensions = [freshness, error_rate, cb_health, coverage]

    weighted_score = sum(d.score * d.weight for d in dimensions)
    weighted_score = round(weighted_score, 1)

    incidents = get_recent_incidents(hours=24)

    return AggregateHealth(
        score=weighted_score,
        grade=_score_to_grade(weighted_score),
        dimensions=dimensions,
        incidents=incidents,
        computed_at=datetime.now(UTC),
    )
