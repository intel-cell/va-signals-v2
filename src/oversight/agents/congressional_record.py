"""Congressional Record source agent."""

import re
from datetime import datetime, timezone
from typing import Optional

from .base import OversightAgent, RawEvent, TimestampResult


class CongressionalRecordAgent(OversightAgent):
    """Agent for fetching VA-related Congressional Record entries."""

    source_type = "congressional_record"

    def __init__(self):
        self.search_terms = ["veterans affairs", "VA ", "Department of Veterans"]

    def fetch_new(self, since: Optional[datetime]) -> list[RawEvent]:
        """
        Fetch new Congressional Record entries.

        Note: Would use Congress.gov API or GovInfo bulk data.
        """
        # Placeholder - would need Congress.gov API integration
        return []

    def backfill(self, start: datetime, end: datetime) -> list[RawEvent]:
        """Backfill historical entries."""
        return []

    def extract_timestamps(self, raw: RawEvent) -> TimestampResult:
        """Extract timestamps from Congressional Record entry."""
        pub_timestamp = raw.metadata.get("date")
        pub_precision = "date" if pub_timestamp else "unknown"
        pub_source = "extracted" if pub_timestamp else "missing"

        return TimestampResult(
            pub_timestamp=pub_timestamp,
            pub_precision=pub_precision,
            pub_source=pub_source,
        )

    def extract_canonical_refs(self, raw: RawEvent) -> dict:
        """Extract Congressional Record reference."""
        refs = {}

        # Look for CR page references like "H1234" or "S5678"
        cr_pattern = re.compile(r"\b([HS]\d{4,})\b")
        match = cr_pattern.search(raw.url)
        if match:
            refs["cr_page"] = match.group(1)

        return refs
