"""Congressional Research Service (CRS) source agent."""

import re
from datetime import datetime, timezone
from typing import Optional

import feedparser

from .base import OversightAgent, RawEvent, TimestampResult


CRS_RSS_URL = "https://www.everycrsreport.com/rss.xml"
CRS_REPORT_PATTERN = re.compile(r"(R\d{5}|RL\d{5}|RS\d{5}|IF\d{5})", re.IGNORECASE)

# Keywords for VA-related reports
VA_KEYWORDS = [
    "veterans affairs",
    "VA ",
    "veteran",
    "GI Bill",
    "TRICARE",
    "military health",
    "VBA",
    "VHA",
]


class CRSAgent(OversightAgent):
    """Agent for fetching CRS reports related to VA."""

    source_type = "crs"

    def __init__(self, rss_url: str = CRS_RSS_URL):
        self.rss_url = rss_url
        self.va_keywords = VA_KEYWORDS

    def _is_va_related(self, title: str) -> bool:
        """Check if report title is VA-related."""
        title_lower = title.lower()
        return any(kw.lower() in title_lower for kw in self.va_keywords)

    def fetch_new(self, since: Optional[datetime]) -> list[RawEvent]:
        """Fetch new CRS reports from RSS feed."""
        feed = feedparser.parse(self.rss_url)
        events = []

        for entry in feed.entries:
            title = entry.get("title", "")

            # Filter to VA-related content
            if not self._is_va_related(title):
                continue

            pub_date = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

            if since and pub_date and pub_date < since:
                continue

            fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            events.append(
                RawEvent(
                    url=entry.link,
                    title=title,
                    raw_html="",  # RSS feed doesn't include content
                    fetched_at=fetched_at,
                    excerpt=None,
                    metadata={
                        "published": getattr(entry, "published", None),
                        "guid": getattr(entry, "id", None),
                    },
                )
            )

        return events

    def backfill(self, start: datetime, end: datetime) -> list[RawEvent]:
        """Backfill - RSS only has recent items."""
        return self.fetch_new(since=None)

    def extract_timestamps(self, raw: RawEvent) -> TimestampResult:
        """Extract timestamps from CRS report."""
        pub_timestamp = None
        pub_precision = "unknown"
        pub_source = "missing"

        published = raw.metadata.get("published")
        if published:
            try:
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(published)
                pub_timestamp = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                pub_precision = "date"
                pub_source = "extracted"
            except (ValueError, TypeError):
                pass

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
