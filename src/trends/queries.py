"""
Trend Query Functions

Provides query interfaces for retrieving historical trend data.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from ..db import connect, execute

logger = logging.getLogger(__name__)


def _date_range(days: int) -> tuple[str, str]:
    """Get date range for last N days."""
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=days)
    return start_date.isoformat(), end_date.isoformat()


def get_signal_trends(
    days: int = 30,
    trigger_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    """
    Get signal firing trends over time.

    Args:
        days: Number of days to look back (default: 30)
        trigger_id: Optional filter by trigger ID
        start_date: Optional start date (overrides days)
        end_date: Optional end date (overrides days)

    Returns:
        List of trend records
    """
    if start_date is None or end_date is None:
        start_date, end_date = _date_range(days)

    con = connect()

    query = """
        SELECT date, trigger_id, signal_count, suppressed_count
        FROM trend_daily_signals
        WHERE date BETWEEN :start_date AND :end_date
    """
    params: dict[str, Any] = {"start_date": start_date, "end_date": end_date}

    if trigger_id:
        query += " AND trigger_id = :trigger_id"
        params["trigger_id"] = trigger_id

    query += " ORDER BY date ASC, trigger_id ASC"

    cur = execute(con, query, params)
    columns = [desc[0] for desc in cur.description]
    rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    con.close()

    return rows


def get_signal_trends_summary(days: int = 30) -> dict[str, Any]:
    """
    Get summary statistics for signal trends.

    Args:
        days: Number of days to analyze

    Returns:
        Summary dict with totals, averages, and top triggers
    """
    start_date, end_date = _date_range(days)

    con = connect()

    # Total signals
    cur = execute(
        con,
        """
        SELECT
            SUM(signal_count) as total_signals,
            SUM(suppressed_count) as total_suppressed,
            COUNT(DISTINCT date) as days_with_data
        FROM trend_daily_signals
        WHERE date BETWEEN :start_date AND :end_date
        """,
        {"start_date": start_date, "end_date": end_date},
    )
    row = cur.fetchone()
    total_signals = row[0] or 0
    total_suppressed = row[1] or 0
    days_with_data = row[2] or 0

    # Top triggers
    cur = execute(
        con,
        """
        SELECT trigger_id, SUM(signal_count) as total
        FROM trend_daily_signals
        WHERE date BETWEEN :start_date AND :end_date
        GROUP BY trigger_id
        ORDER BY total DESC
        LIMIT 10
        """,
        {"start_date": start_date, "end_date": end_date},
    )
    top_triggers = [{"trigger_id": row[0], "count": row[1]} for row in cur.fetchall()]

    # Daily average
    avg_daily = total_signals / days_with_data if days_with_data > 0 else 0

    con.close()

    return {
        "period_days": days,
        "start_date": start_date,
        "end_date": end_date,
        "total_signals": total_signals,
        "total_suppressed": total_suppressed,
        "avg_daily_signals": round(avg_daily, 1),
        "suppression_rate": round(total_suppressed / total_signals * 100, 1) if total_signals > 0 else 0,
        "top_triggers": top_triggers,
    }


def get_source_health_trends(
    days: int = 30,
    source_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    Get source health metrics over time.

    Args:
        days: Number of days to look back
        source_id: Optional filter by source ID

    Returns:
        List of trend records
    """
    start_date, end_date = _date_range(days)

    con = connect()

    query = """
        SELECT date, source_id, run_count, success_count, error_count,
               no_data_count, total_docs, success_rate
        FROM trend_daily_source_health
        WHERE date BETWEEN :start_date AND :end_date
    """
    params: dict[str, Any] = {"start_date": start_date, "end_date": end_date}

    if source_id:
        query += " AND source_id = :source_id"
        params["source_id"] = source_id

    query += " ORDER BY date ASC, source_id ASC"

    cur = execute(con, query, params)
    columns = [desc[0] for desc in cur.description]
    rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    con.close()

    return rows


def get_source_health_summary(days: int = 30) -> dict[str, Any]:
    """
    Get summary of source health over time.

    Args:
        days: Number of days to analyze

    Returns:
        Summary with per-source stats
    """
    start_date, end_date = _date_range(days)

    con = connect()

    cur = execute(
        con,
        """
        SELECT source_id,
               SUM(run_count) as total_runs,
               SUM(success_count) as successes,
               SUM(error_count) as errors,
               SUM(total_docs) as docs_fetched,
               AVG(success_rate) as avg_success_rate
        FROM trend_daily_source_health
        WHERE date BETWEEN :start_date AND :end_date
        GROUP BY source_id
        ORDER BY total_runs DESC
        """,
        {"start_date": start_date, "end_date": end_date},
    )

    sources = []
    for row in cur.fetchall():
        sources.append({
            "source_id": row[0],
            "total_runs": row[1] or 0,
            "successes": row[2] or 0,
            "errors": row[3] or 0,
            "docs_fetched": row[4] or 0,
            "avg_success_rate": round(row[5] or 0, 1),
        })

    con.close()

    return {
        "period_days": days,
        "start_date": start_date,
        "end_date": end_date,
        "sources": sources,
    }


def get_oversight_trends(weeks: int = 12) -> list[dict[str, Any]]:
    """
    Get weekly oversight trends.

    Args:
        weeks: Number of weeks to look back

    Returns:
        List of weekly oversight records
    """
    con = connect()

    cur = execute(
        con,
        """
        SELECT week_start, week_end, total_events, escalations, deviations,
               by_source_json, by_theme_json
        FROM trend_weekly_oversight
        ORDER BY week_start DESC
        LIMIT :weeks
        """,
        {"weeks": weeks},
    )

    columns = [desc[0] for desc in cur.description]
    rows = []
    for row in cur.fetchall():
        record = dict(zip(columns, row))
        # Parse JSON fields
        record["by_source"] = json.loads(record.pop("by_source_json", "{}") or "{}")
        record["by_theme"] = json.loads(record.pop("by_theme_json", "{}") or "{}")
        rows.append(record)

    con.close()

    # Return in chronological order
    return list(reversed(rows))


def get_battlefield_trends(days: int = 30) -> list[dict[str, Any]]:
    """
    Get daily battlefield status trends.

    Args:
        days: Number of days to look back

    Returns:
        List of daily battlefield records
    """
    start_date, end_date = _date_range(days)

    con = connect()

    cur = execute(
        con,
        """
        SELECT date, total_vehicles, active_vehicles, critical_gates, alerts_count,
               by_type_json, by_posture_json, by_stage_json
        FROM trend_daily_battlefield
        WHERE date BETWEEN :start_date AND :end_date
        ORDER BY date ASC
        """,
        {"start_date": start_date, "end_date": end_date},
    )

    columns = [desc[0] for desc in cur.description]
    rows = []
    for row in cur.fetchall():
        record = dict(zip(columns, row))
        # Parse JSON fields
        record["by_type"] = json.loads(record.pop("by_type_json", "{}") or "{}")
        record["by_posture"] = json.loads(record.pop("by_posture_json", "{}") or "{}")
        record["by_stage"] = json.loads(record.pop("by_stage_json", "{}") or "{}")
        rows.append(record)

    con.close()

    return rows


def get_battlefield_trends_summary(days: int = 30) -> dict[str, Any]:
    """
    Get battlefield trends summary.

    Args:
        days: Number of days to analyze

    Returns:
        Summary with vehicle counts and trends
    """
    trends = get_battlefield_trends(days)

    if not trends:
        return {
            "period_days": days,
            "current_vehicles": 0,
            "avg_critical_gates": 0,
            "total_alerts": 0,
        }

    latest = trends[-1] if trends else {}
    total_alerts = sum(t.get("alerts_count", 0) for t in trends)
    avg_critical = sum(t.get("critical_gates", 0) for t in trends) / len(trends) if trends else 0

    return {
        "period_days": days,
        "current_vehicles": latest.get("total_vehicles", 0),
        "current_active": latest.get("active_vehicles", 0),
        "current_critical_gates": latest.get("critical_gates", 0),
        "avg_critical_gates": round(avg_critical, 1),
        "total_alerts": total_alerts,
        "by_type": latest.get("by_type", {}),
        "by_posture": latest.get("by_posture", {}),
    }
