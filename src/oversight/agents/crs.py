"""Congressional Research Service (CRS) source agent."""

import re
from datetime import datetime, timezone
from typing import Optional

import httpx

from .base import OversightAgent, RawEvent, TimestampResult


CRS_SEARCH_URL = "https://crsreports.congress.gov/search/results"
CRS_REPORT_PATTERN = re.compile(r"(R\d{5}|RL\d{5}|RS\d{5})", re.IGNORECASE)


class CRSAgent(OversightAgent):
    """Agent for fetching CRS reports related to VA."""

    source_type = "crs"

    def __init__(self):
        self.search_terms = ["veterans affairs", "VA benefits", "VA healthcare"]

    def fetch_new(self, since: Optional[datetime]) -> list[RawEvent]:
        """
        Fetch new CRS reports.

        Note: CRS doesn't have a public API, so this is a placeholder
        that would need web scraping or API access.
        """
        # Placeholder - would need to implement web scraping
        # or use an API if available
        return []

    def backfill(self, start: datetime, end: datetime) -> list[RawEvent]:
        """Backfill historical CRS reports."""
        return []

    def extract_timestamps(self, raw: RawEvent) -> TimestampResult:
        """Extract timestamps from CRS report."""
        pub_timestamp = raw.metadata.get("published")
        pub_precision = "date" if pub_timestamp else "unknown"
        pub_source = "extracted" if pub_timestamp else "missing"

        return TimestampResult(
            pub_timestamp=pub_timestamp,
            pub_precision=pub_precision,
            pub_source=pub_source,
        )

    def extract_canonical_refs(self, raw: RawEvent) -> dict:
        """Extract CRS report number."""
        refs = {}
        combined = f"{raw.url} {raw.title}"

        match = CRS_REPORT_PATTERN.search(combined)
        if match:
            refs["crs_report"] = match.group(1).upper()

        return refs
