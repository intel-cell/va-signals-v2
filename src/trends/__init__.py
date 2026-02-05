"""
Trend Analysis Module

Provides historical aggregation and trend analysis for:
- Signal firing patterns over time
- Source health metrics
- Oversight activity summaries
- Battlefield status changes
"""

from .aggregator import (
    aggregate_daily_signals,
    aggregate_daily_source_health,
    aggregate_weekly_oversight,
    aggregate_daily_battlefield,
    run_all_aggregations,
)

from .queries import (
    get_signal_trends,
    get_signal_trends_summary,
    get_source_health_trends,
    get_source_health_summary,
    get_oversight_trends,
    get_battlefield_trends,
    get_battlefield_trends_summary,
)

__all__ = [
    "aggregate_daily_signals",
    "aggregate_daily_source_health",
    "aggregate_weekly_oversight",
    "aggregate_daily_battlefield",
    "run_all_aggregations",
    "get_signal_trends",
    "get_signal_trends_summary",
    "get_source_health_trends",
    "get_source_health_summary",
    "get_oversight_trends",
    "get_battlefield_trends",
    "get_battlefield_trends_summary",
]
