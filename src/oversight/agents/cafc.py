"""Court of Appeals for the Federal Circuit (CAFC) source agent."""

import re
from datetime import datetime, timezone
from typing import Optional

from .base import OversightAgent, RawEvent, TimestampResult


CAFC_CASE_PATTERN = re.compile(r"(\d{4})-(\d{4})", re.IGNORECASE)


class CAFCAgent(OversightAgent):
    """Agent for fetching CAFC veterans case decisions."""

    source_type = "cafc"

    def __init__(self):
        self.va_parties = [
            "McDonough",  # Current VA Secretary
            "Wilkie",
            "Shulkin",
            "Secretary of Veterans Affairs",
            "Department of Veterans Affairs",
        ]

    def fetch_new(self, since: Optional[datetime]) -> list[RawEvent]:
        """
        Fetch new CAFC decisions.

        Note: CAFC has an RSS feed for opinions.
        Would need to filter for VA-related cases.
        """
        # Placeholder - would need CAFC opinion feed integration
        # and filtering for VA cases
        return []

    def backfill(self, start: datetime, end: datetime) -> list[RawEvent]:
        """Backfill historical CAFC decisions."""
        return []

    def extract_timestamps(self, raw: RawEvent) -> TimestampResult:
        """Extract timestamps from CAFC decision."""
        pub_timestamp = raw.metadata.get("decision_date")
        pub_precision = "date" if pub_timestamp else "unknown"
        pub_source = "extracted" if pub_timestamp else "missing"

        return TimestampResult(
            pub_timestamp=pub_timestamp,
            pub_precision=pub_precision,
            pub_source=pub_source,
        )

    def extract_canonical_refs(self, raw: RawEvent) -> dict:
        """Extract CAFC case number."""
        refs = {}
        combined = f"{raw.url} {raw.title}"

        match = CAFC_CASE_PATTERN.search(combined)
        if match:
            refs["cafc_case"] = f"{match.group(1)}-{match.group(2)}"

        # Check if precedential
        if "precedential" in raw.title.lower() or raw.metadata.get("precedential"):
            refs["is_precedential"] = True

        return refs
