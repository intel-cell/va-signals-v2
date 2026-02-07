"""Shared helpers used across multiple routers."""

import json
from datetime import UTC, datetime


def parse_errors_json(errors_json: str) -> list[str]:
    """Parse errors_json column, handling malformed data gracefully."""
    try:
        errors = json.loads(errors_json) if errors_json else []
        return errors if isinstance(errors, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
