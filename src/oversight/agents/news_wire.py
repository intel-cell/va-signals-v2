"""News Wire source agent - AP, Reuters, etc."""

import re
from datetime import datetime, timezone
from typing import Optional

from .base import OversightAgent, RawEvent, TimestampResult


class NewsWireAgent(OversightAgent):
    """Agent for fetching VA-related news wire stories."""

    source_type = "news_wire"

    def __init__(self):
        self.search_terms = [
            "veterans affairs",
            "VA hospital",
            "VA benefits",
            "VA secretary",
        ]

    def fetch_new(self, since: Optional[datetime]) -> list[RawEvent]:
        """
        Fetch new news wire stories.

        Note: Would require news API subscription (AP, Reuters, etc.)
        or Google News RSS parsing.
        """
        # Placeholder - would need news API integration
        return []

    def backfill(self, start: datetime, end: datetime) -> list[RawEvent]:
        """Backfill historical stories."""
        return []

    def extract_timestamps(self, raw: RawEvent) -> TimestampResult:
        """Extract timestamps from news story."""
        pub_timestamp = raw.metadata.get("published")
        pub_precision = "datetime" if pub_timestamp else "unknown"
        pub_source = "extracted" if pub_timestamp else "missing"

        return TimestampResult(
            pub_timestamp=pub_timestamp,
            pub_precision=pub_precision,
            pub_source=pub_source,
        )

    def extract_canonical_refs(self, raw: RawEvent) -> dict:
        """Extract references from news story."""
        refs = {}

        # Look for bill references in story
        bill_pattern = re.compile(r"(H\.?R\.?\s*\d+|S\.?\s*\d+)", re.IGNORECASE)
        match = bill_pattern.search(raw.raw_html)
        if match:
            refs["bill_mentioned"] = match.group(1)

        return refs
