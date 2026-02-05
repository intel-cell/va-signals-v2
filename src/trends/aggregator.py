"""
Trend Aggregator

Computes and stores historical aggregations for trend analysis.
Designed to run as a nightly job after pipeline completion.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from ..db import connect, execute

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    """Get current UTC datetime."""
    return datetime.now(timezone.utc)


def _date_str(dt: datetime) -> str:
    """Convert datetime to ISO date string."""
    return dt.date().isoformat()


def aggregate_daily_signals(target_date: str | None = None) -> dict[str, Any]:
    """
    Aggregate signal firing counts for a given date.

    Args:
        target_date: ISO date string (default: yesterday)

    Returns:
        Stats dict with aggregation results
    """
    if target_date is None:
        target_date = _date_str(_utc_now() - timedelta(days=1))

    logger.info(f"Aggregating daily signals for {target_date}")

    con = connect()

    # Get signal counts by trigger
    cur = execute(
        con,
        """
        SELECT trigger_id,
               COUNT(*) as signal_count,
               SUM(CASE WHEN suppressed = 1 THEN 1 ELSE 0 END) as suppressed_count
        FROM signal_audit_log
        WHERE date(fired_at) = :target_date
        GROUP BY trigger_id
        """,
        {"target_date": target_date},
    )

    rows = cur.fetchall()
    inserted = 0

    for row in rows:
        trigger_id, signal_count, suppressed_count = row

        execute(
            con,
            """
            INSERT INTO trend_daily_signals (date, trigger_id, signal_count, suppressed_count)
            VALUES (:date, :trigger_id, :signal_count, :suppressed_count)
            ON CONFLICT(date, trigger_id) DO UPDATE SET
                signal_count = :signal_count,
                suppressed_count = :suppressed_count
            """,
            {
                "date": target_date,
                "trigger_id": trigger_id,
                "signal_count": signal_count,
                "suppressed_count": suppressed_count or 0,
            },
        )
        inserted += 1

    con.commit()
    con.close()

    logger.info(f"Aggregated {inserted} trigger records for {target_date}")
    return {"date": target_date, "triggers_aggregated": inserted}


def aggregate_daily_source_health(target_date: str | None = None) -> dict[str, Any]:
    """
    Aggregate source health metrics for a given date.

    Args:
        target_date: ISO date string (default: yesterday)

    Returns:
        Stats dict with aggregation results
    """
    if target_date is None:
        target_date = _date_str(_utc_now() - timedelta(days=1))

    logger.info(f"Aggregating source health for {target_date}")

    con = connect()

    # Get source run stats
    cur = execute(
        con,
        """
        SELECT source_id,
               COUNT(*) as run_count,
               SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) as success_count,
               SUM(CASE WHEN status = 'ERROR' THEN 1 ELSE 0 END) as error_count,
               SUM(CASE WHEN status = 'NO_DATA' THEN 1 ELSE 0 END) as no_data_count,
               SUM(records_fetched) as total_docs
        FROM source_runs
        WHERE date(started_at) = :target_date
        GROUP BY source_id
        """,
        {"target_date": target_date},
    )

    rows = cur.fetchall()
    inserted = 0

    for row in rows:
        source_id, run_count, success_count, error_count, no_data_count, total_docs = row
        success_rate = (success_count / run_count * 100) if run_count > 0 else 0

        execute(
            con,
            """
            INSERT INTO trend_daily_source_health
                (date, source_id, run_count, success_count, error_count,
                 no_data_count, total_docs, success_rate)
            VALUES
                (:date, :source_id, :run_count, :success_count, :error_count,
                 :no_data_count, :total_docs, :success_rate)
            ON CONFLICT(date, source_id) DO UPDATE SET
                run_count = :run_count,
                success_count = :success_count,
                error_count = :error_count,
                no_data_count = :no_data_count,
                total_docs = :total_docs,
                success_rate = :success_rate
            """,
            {
                "date": target_date,
                "source_id": source_id,
                "run_count": run_count,
                "success_count": success_count or 0,
                "error_count": error_count or 0,
                "no_data_count": no_data_count or 0,
                "total_docs": total_docs or 0,
                "success_rate": round(success_rate, 2),
            },
        )
        inserted += 1

    con.commit()
    con.close()

    logger.info(f"Aggregated {inserted} source health records for {target_date}")
    return {"date": target_date, "sources_aggregated": inserted}


def aggregate_weekly_oversight(week_start: str | None = None) -> dict[str, Any]:
    """
    Aggregate oversight metrics for a given week.

    Args:
        week_start: ISO date string for Monday of target week (default: last Monday)

    Returns:
        Stats dict with aggregation results
    """
    if week_start is None:
        # Find last Monday
        today = _utc_now().date()
        days_since_monday = today.weekday()
        last_monday = today - timedelta(days=days_since_monday + 7)
        week_start = last_monday.isoformat()

    week_end = (datetime.fromisoformat(week_start).date() + timedelta(days=6)).isoformat()

    logger.info(f"Aggregating weekly oversight for {week_start} to {week_end}")

    con = connect()

    # Get oversight event stats
    cur = execute(
        con,
        """
        SELECT
            COUNT(*) as total_events,
            SUM(CASE WHEN is_escalation = 1 THEN 1 ELSE 0 END) as escalations,
            SUM(CASE WHEN is_deviation = 1 THEN 1 ELSE 0 END) as deviations
        FROM om_events
        WHERE date(pub_timestamp) BETWEEN :week_start AND :week_end
        """,
        {"week_start": week_start, "week_end": week_end},
    )

    row = cur.fetchone()
    total_events = row[0] or 0
    escalations = row[1] or 0
    deviations = row[2] or 0

    # Get by source breakdown
    cur = execute(
        con,
        """
        SELECT primary_source_type, COUNT(*) as count
        FROM om_events
        WHERE date(pub_timestamp) BETWEEN :week_start AND :week_end
        GROUP BY primary_source_type
        """,
        {"week_start": week_start, "week_end": week_end},
    )
    by_source = {row[0]: row[1] for row in cur.fetchall()}

    # Get by theme breakdown
    cur = execute(
        con,
        """
        SELECT theme, COUNT(*) as count
        FROM om_events
        WHERE date(pub_timestamp) BETWEEN :week_start AND :week_end
          AND theme IS NOT NULL
        GROUP BY theme
        """,
        {"week_start": week_start, "week_end": week_end},
    )
    by_theme = {row[0]: row[1] for row in cur.fetchall()}

    execute(
        con,
        """
        INSERT INTO trend_weekly_oversight
            (week_start, week_end, total_events, escalations, deviations,
             by_source_json, by_theme_json)
        VALUES
            (:week_start, :week_end, :total_events, :escalations, :deviations,
             :by_source_json, :by_theme_json)
        ON CONFLICT(week_start) DO UPDATE SET
            week_end = :week_end,
            total_events = :total_events,
            escalations = :escalations,
            deviations = :deviations,
            by_source_json = :by_source_json,
            by_theme_json = :by_theme_json
        """,
        {
            "week_start": week_start,
            "week_end": week_end,
            "total_events": total_events,
            "escalations": escalations,
            "deviations": deviations,
            "by_source_json": json.dumps(by_source),
            "by_theme_json": json.dumps(by_theme),
        },
    )

    con.commit()
    con.close()

    logger.info(f"Aggregated weekly oversight: {total_events} events, {escalations} escalations")
    return {
        "week_start": week_start,
        "week_end": week_end,
        "total_events": total_events,
        "escalations": escalations,
        "deviations": deviations,
    }


def aggregate_daily_battlefield(target_date: str | None = None) -> dict[str, Any]:
    """
    Aggregate battlefield status for a given date.

    Args:
        target_date: ISO date string (default: yesterday)

    Returns:
        Stats dict with aggregation results
    """
    if target_date is None:
        target_date = _date_str(_utc_now() - timedelta(days=1))

    logger.info(f"Aggregating battlefield status for {target_date}")

    con = connect()

    # Get vehicle counts
    cur = execute(
        con,
        """
        SELECT
            COUNT(*) as total_vehicles,
            SUM(CASE WHEN current_stage NOT IN ('enacted', 'expired', 'vetoed') THEN 1 ELSE 0 END) as active_vehicles
        FROM bf_vehicles
        """,
        {},
    )
    row = cur.fetchone()
    total_vehicles = row[0] or 0
    active_vehicles = row[1] or 0

    # Get critical gates (events in next 7 days)
    cutoff_date = (datetime.fromisoformat(target_date).date() + timedelta(days=7)).isoformat()
    cur = execute(
        con,
        """
        SELECT COUNT(*)
        FROM bf_calendar_events
        WHERE date BETWEEN :target_date AND :cutoff_date
          AND importance = 'critical'
          AND passed = 0
          AND cancelled = 0
        """,
        {"target_date": target_date, "cutoff_date": cutoff_date},
    )
    critical_gates = cur.fetchone()[0] or 0

    # Get alerts count for the day
    cur = execute(
        con,
        """
        SELECT COUNT(*)
        FROM bf_gate_alerts
        WHERE date(timestamp) = :target_date
        """,
        {"target_date": target_date},
    )
    alerts_count = cur.fetchone()[0] or 0

    # Get by type breakdown
    cur = execute(
        con,
        """
        SELECT vehicle_type, COUNT(*) as count
        FROM bf_vehicles
        GROUP BY vehicle_type
        """,
        {},
    )
    by_type = {row[0]: row[1] for row in cur.fetchall()}

    # Get by posture breakdown
    cur = execute(
        con,
        """
        SELECT our_posture, COUNT(*) as count
        FROM bf_vehicles
        GROUP BY our_posture
        """,
        {},
    )
    by_posture = {row[0]: row[1] for row in cur.fetchall()}

    # Get by stage breakdown
    cur = execute(
        con,
        """
        SELECT current_stage, COUNT(*) as count
        FROM bf_vehicles
        GROUP BY current_stage
        """,
        {},
    )
    by_stage = {row[0]: row[1] for row in cur.fetchall()}

    execute(
        con,
        """
        INSERT INTO trend_daily_battlefield
            (date, total_vehicles, active_vehicles, critical_gates, alerts_count,
             by_type_json, by_posture_json, by_stage_json)
        VALUES
            (:date, :total_vehicles, :active_vehicles, :critical_gates, :alerts_count,
             :by_type_json, :by_posture_json, :by_stage_json)
        ON CONFLICT(date) DO UPDATE SET
            total_vehicles = :total_vehicles,
            active_vehicles = :active_vehicles,
            critical_gates = :critical_gates,
            alerts_count = :alerts_count,
            by_type_json = :by_type_json,
            by_posture_json = :by_posture_json,
            by_stage_json = :by_stage_json
        """,
        {
            "date": target_date,
            "total_vehicles": total_vehicles,
            "active_vehicles": active_vehicles,
            "critical_gates": critical_gates,
            "alerts_count": alerts_count,
            "by_type_json": json.dumps(by_type),
            "by_posture_json": json.dumps(by_posture),
            "by_stage_json": json.dumps(by_stage),
        },
    )

    con.commit()
    con.close()

    logger.info(f"Aggregated battlefield: {total_vehicles} vehicles, {critical_gates} critical gates")
    return {
        "date": target_date,
        "total_vehicles": total_vehicles,
        "active_vehicles": active_vehicles,
        "critical_gates": critical_gates,
        "alerts_count": alerts_count,
    }


def run_all_aggregations(target_date: str | None = None) -> dict[str, Any]:
    """
    Run all aggregation jobs.

    Args:
        target_date: ISO date string (default: yesterday)

    Returns:
        Combined results from all aggregations
    """
    logger.info("Running all trend aggregations...")

    results = {
        "signals": aggregate_daily_signals(target_date),
        "source_health": aggregate_daily_source_health(target_date),
        "oversight": aggregate_weekly_oversight(),
        "battlefield": aggregate_daily_battlefield(target_date),
    }

    logger.info("All trend aggregations complete")
    return results
