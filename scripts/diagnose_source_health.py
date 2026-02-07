"""
Diagnose source health from source_runs table.

Read-only diagnostic script that reports success/failure rates per source
and identifies common error patterns.

Run with: python -m scripts.diagnose_source_health [--source SOURCE_ID]
"""

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import connect, execute

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# Known error pattern keywords
ERROR_PATTERNS = {
    "missing API key": ["api_key", "api key", "apikey", "unauthorized", "401"],
    "rate limit": ["rate limit", "429", "too many requests", "throttl"],
    "timeout": ["timeout", "timed out", "read timed out"],
    "connection error": [
        "connection",
        "connect",
        "refused",
        "reset",
        "network",
        "ssl",
        "certificate",
    ],
    "parse error": ["json", "parse", "decode", "unexpected", "malformed"],
    "not found": ["404", "not found"],
    "server error": ["500", "502", "503", "504", "internal server error"],
}


def classify_error(error_text: str) -> str:
    """Classify an error string into a known pattern category."""
    lower = error_text.lower()
    for pattern_name, keywords in ERROR_PATTERNS.items():
        for kw in keywords:
            if kw in lower:
                return pattern_name
    return "other"


def diagnose(source_filter: str | None = None) -> None:
    """Run diagnostics on source_runs and print results."""
    con = connect()

    # Get status counts per source
    sql = """
        SELECT source_id, status, COUNT(*) as cnt
        FROM source_runs
    """
    params: dict = {}
    if source_filter:
        sql += " WHERE source_id = :source_id"
        params["source_id"] = source_filter
    sql += " GROUP BY source_id, status ORDER BY source_id, status"

    cur = execute(con, sql, params)
    rows = cur.fetchall()

    if not rows:
        print("No source_runs data found.")
        con.close()
        return

    # Build per-source stats
    source_stats: dict[str, dict[str, int]] = {}
    for source_id, status, cnt in rows:
        if source_id not in source_stats:
            source_stats[source_id] = {}
        source_stats[source_id][status] = cnt

    # Print status table
    print()
    print("=" * 80)
    print("SOURCE HEALTH REPORT")
    print("=" * 80)
    print()
    print(f"{'Source':<30} {'Total':>7} {'SUCCESS':>9} {'NO_DATA':>9} {'ERROR':>7} {'Err%':>6}")
    print("-" * 80)

    for source_id in sorted(source_stats):
        counts = source_stats[source_id]
        total = sum(counts.values())
        success = counts.get("SUCCESS", 0)
        no_data = counts.get("NO_DATA", 0)
        error = counts.get("ERROR", 0)
        err_pct = (error / total * 100) if total > 0 else 0.0
        print(
            f"{source_id:<30} {total:>7} {success:>9} {no_data:>9} {error:>7} {err_pct:>5.1f}%"
        )

    print("-" * 80)

    # Error pattern analysis
    err_sql = """
        SELECT source_id, errors_json
        FROM source_runs
        WHERE status = 'ERROR' AND errors_json IS NOT NULL AND errors_json != '[]'
    """
    err_params: dict = {}
    if source_filter:
        err_sql += " AND source_id = :source_id"
        err_params["source_id"] = source_filter

    cur = execute(con, err_sql, err_params)
    error_rows = cur.fetchall()
    con.close()

    if not error_rows:
        print("\nNo error details to analyze.")
        return

    pattern_counts: Counter = Counter()
    source_pattern_counts: dict[str, Counter] = {}

    for source_id, errors_json in error_rows:
        try:
            errors = json.loads(errors_json) if errors_json else []
        except (json.JSONDecodeError, TypeError):
            errors = [str(errors_json)]

        if isinstance(errors, str):
            errors = [errors]

        for err in errors:
            if not isinstance(err, str):
                err = str(err)
            pattern = classify_error(err)
            pattern_counts[pattern] += 1
            if source_id not in source_pattern_counts:
                source_pattern_counts[source_id] = Counter()
            source_pattern_counts[source_id][pattern] += 1

    print()
    print("ERROR PATTERN ANALYSIS")
    print("-" * 40)
    for pattern, count in pattern_counts.most_common():
        print(f"  {pattern:<25} {count:>5}")

    if source_filter and source_filter in source_pattern_counts:
        print()
        print(f"Error patterns for {source_filter}:")
        for pattern, count in source_pattern_counts[source_filter].most_common():
            print(f"  {pattern:<25} {count:>5}")

    print()


def main():
    parser = argparse.ArgumentParser(description="Diagnose source health from source_runs")
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="Filter to a specific source_id",
    )
    args = parser.parse_args()

    diagnose(source_filter=args.source)
    return 0


if __name__ == "__main__":
    sys.exit(main())
