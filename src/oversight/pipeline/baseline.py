"""Baseline builder for oversight events - rolling summaries and topic distribution."""

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from src.db import connect, execute, insert_returning_id


@dataclass
class BaselineSummary:
    """Summary of baseline period for a source/theme."""

    source_type: str
    theme: Optional[str]
    window_start: str
    window_end: str
    event_count: int
    summary: str
    topic_distribution: dict = field(default_factory=dict)


def _get_events_in_window(
    source_type: str,
    theme: Optional[str],
    window_start: str,
    window_end: str,
) -> list[dict]:
    """Get events in the specified window."""
    con = connect()

    query = """
        SELECT event_id, event_type, theme, title, summary, pub_timestamp
        FROM om_events
        WHERE primary_source_type = :source_type
          AND pub_timestamp >= :window_start
          AND pub_timestamp <= :window_end
    """
    params: dict[str, object] = {
        "source_type": source_type,
        "window_start": window_start,
        "window_end": window_end,
    }

    if theme:
        query += " AND theme = :theme"
        params["theme"] = theme

    query += " ORDER BY pub_timestamp DESC"

    cur = execute(con, query, params)
    rows = cur.fetchall()
    con.close()

    return [
        {
            "event_id": row[0],
            "event_type": row[1],
            "theme": row[2],
            "title": row[3],
            "summary": row[4],
            "pub_timestamp": row[5],
        }
        for row in rows
    ]


def compute_topic_distribution(events: list[dict]) -> dict:
    """
    Compute topic distribution from event titles and summaries.

    Uses simple keyword extraction - could be enhanced with LLM.

    Args:
        events: List of event dicts with title and summary

    Returns:
        Dict of topic -> frequency (0-1)
    """
    # Common VA-related topics to look for
    topic_keywords = {
        "healthcare": ["healthcare", "health care", "medical", "hospital", "clinic"],
        "benefits": ["benefits", "compensation", "pension", "disability"],
        "claims": ["claims", "claim", "processing", "backlog"],
        "wait_times": ["wait time", "wait times", "delays", "scheduling"],
        "staffing": ["staffing", "personnel", "employees", "hiring"],
        "budget": ["budget", "funding", "appropriations", "spending"],
        "fraud": ["fraud", "waste", "abuse", "misconduct"],
        "technology": ["technology", "it ", "systems", "electronic"],
        "mental_health": ["mental health", "ptsd", "suicide", "counseling"],
        "housing": ["housing", "homeless", "hud-vash"],
    }

    # Combine all text
    all_text = " ".join(
        f"{e.get('title', '')} {e.get('summary', '')}".lower()
        for e in events
    )

    # Count topic occurrences
    topic_counts = Counter()
    for topic, keywords in topic_keywords.items():
        for keyword in keywords:
            count = len(re.findall(rf"\b{re.escape(keyword)}\b", all_text))
            topic_counts[topic] += count

    # Normalize to frequencies
    total = sum(topic_counts.values())
    if total == 0:
        return {}

    return {
        topic: round(count / total, 3)
        for topic, count in topic_counts.most_common(5)
        if count > 0
    }


def _generate_summary(events: list[dict], source_type: str, theme: Optional[str]) -> str:
    """Generate a text summary of the baseline period."""
    count = len(events)
    if count == 0:
        return f"No {source_type} events in baseline period"

    # Get date range
    dates = [e.get("pub_timestamp", "") for e in events if e.get("pub_timestamp")]
    if dates:
        earliest = min(dates)[:10]
        latest = max(dates)[:10]
        date_range = f"from {earliest} to {latest}"
    else:
        date_range = "in baseline period"

    theme_str = f" on {theme}" if theme else ""
    return f"{count} {source_type} events{theme_str} {date_range}"


def build_baseline(
    source_type: str,
    theme: Optional[str] = None,
    window_days: int = 90,
    save: bool = False,
) -> Optional[BaselineSummary]:
    """
    Build a baseline summary for a source/theme.

    Args:
        source_type: Source type to build baseline for
        theme: Optional theme filter
        window_days: Number of days in the window
        save: Whether to save to database

    Returns:
        BaselineSummary or None if no events
    """
    # Calculate window
    now = datetime.now(timezone.utc)
    window_end = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    window_start = (now - timedelta(days=window_days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Get events
    events = _get_events_in_window(source_type, theme, window_start, window_end)

    if not events:
        return None

    # Compute topic distribution
    topic_dist = compute_topic_distribution(events)

    # Generate summary
    summary_text = _generate_summary(events, source_type, theme)

    baseline = BaselineSummary(
        source_type=source_type,
        theme=theme,
        window_start=window_start[:10],
        window_end=window_end[:10],
        event_count=len(events),
        summary=summary_text,
        topic_distribution=topic_dist,
    )

    if save:
        _save_baseline(baseline)

    return baseline


def _save_baseline(baseline: BaselineSummary) -> int:
    """Save baseline to database. Returns row ID."""
    con = connect()
    row_id = insert_returning_id(
        con,
        """
        INSERT INTO om_baselines (
            source_type, theme, window_start, window_end,
            event_count, summary, topic_distribution, built_at
        ) VALUES (
            :source_type, :theme, :window_start, :window_end,
            :event_count, :summary, :topic_distribution, :built_at
        )
        """,
        {
            "source_type": baseline.source_type,
            "theme": baseline.theme,
            "window_start": baseline.window_start,
            "window_end": baseline.window_end,
            "event_count": baseline.event_count,
            "summary": baseline.summary,
            "topic_distribution": json.dumps(baseline.topic_distribution),
            "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    )
    con.commit()
    con.close()
    return row_id


def get_latest_baseline(source_type: str, theme: Optional[str] = None) -> Optional[dict]:
    """
    Get the most recent baseline for a source/theme.

    Args:
        source_type: Source type
        theme: Optional theme filter

    Returns:
        Baseline dict or None
    """
    con = connect()

    if theme:
        cur = execute(
            con,
            """
            SELECT id, source_type, theme, window_start, window_end,
                   event_count, summary, topic_distribution, built_at
            FROM om_baselines
            WHERE source_type = :source_type AND theme = :theme
            ORDER BY built_at DESC
            LIMIT 1
            """,
            {"source_type": source_type, "theme": theme},
        )
    else:
        cur = execute(
            con,
            """
            SELECT id, source_type, theme, window_start, window_end,
                   event_count, summary, topic_distribution, built_at
            FROM om_baselines
            WHERE source_type = :source_type AND theme IS NULL
            ORDER BY built_at DESC
            LIMIT 1
            """,
            {"source_type": source_type},
        )

    row = cur.fetchone()
    con.close()

    if not row:
        return None

    return {
        "id": row[0],
        "source_type": row[1],
        "theme": row[2],
        "window_start": row[3],
        "window_end": row[4],
        "event_count": row[5],
        "summary": row[6],
        "topic_distribution": json.loads(row[7]) if row[7] else {},
        "built_at": row[8],
    }


def build_all_baselines(window_days: int = 90, save: bool = True) -> list[BaselineSummary]:
    """
    Build baselines for all source types with events.

    Args:
        window_days: Number of days in the window
        save: Whether to save to database

    Returns:
        List of built baselines
    """
    con = connect()
    cur = execute(con, "SELECT DISTINCT primary_source_type FROM om_events")
    source_types = [row[0] for row in cur.fetchall()]
    con.close()

    baselines = []
    for source_type in source_types:
        baseline = build_baseline(source_type, window_days=window_days, save=save)
        if baseline:
            baselines.append(baseline)

    return baselines
