"""GAO (Government Accountability Office) source agent."""

import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

import feedparser

from .base import OversightAgent, RawEvent, TimestampResult


GAO_RSS_URL = "https://www.gao.gov/rss/reports.xml"
GAO_REPORT_PATTERN = re.compile(r"gao-(\d{2})-(\d+)", re.IGNORECASE)


class GAOAgent(OversightAgent):
    """Agent for fetching GAO reports."""

    source_type = "gao"

    def __init__(self, rss_url: str = GAO_RSS_URL):
        self.rss_url = rss_url

    def fetch_new(self, since: Optional[datetime]) -> list[RawEvent]:
        """Fetch new GAO reports from RSS feed."""
        feed = feedparser.parse(self.rss_url)
        events = []

        for entry in feed.entries:
            # Parse publication date
            pub_date = None
            if hasattr(entry, "published"):
                try:
                    pub_date = parsedate_to_datetime(entry.published)
                except (ValueError, TypeError):
                    pass

            # Skip if older than since
            if since and pub_date and pub_date < since:
                continue

            fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            events.append(
                RawEvent(
                    url=entry.link,
                    title=entry.title,
                    raw_html=getattr(entry, "summary", ""),
                    fetched_at=fetched_at,
                    excerpt=getattr(entry, "summary", "")[:500] if hasattr(entry, "summary") else None,
                    metadata={
                        "published": getattr(entry, "published", None),
                    },
                )
            )

        return events

    def backfill(self, start: datetime, end: datetime) -> list[RawEvent]:
        """
        Backfill historical GAO reports.

        Note: RSS only has recent items. For full backfill,
        would need to use GAO search API.
        """
        # For now, just fetch what's in RSS and filter by date
        all_events = self.fetch_new(since=None)

        filtered = []
        for event in all_events:
            ts = self.extract_timestamps(event)
            if ts.pub_timestamp:
                try:
                    pub_dt = datetime.fromisoformat(ts.pub_timestamp.replace("Z", "+00:00"))
                    if start <= pub_dt <= end:
                        filtered.append(event)
                except (ValueError, TypeError):
                    pass

        return filtered

    def extract_timestamps(self, raw: RawEvent) -> TimestampResult:
        """Extract timestamps from GAO report."""
        pub_timestamp = None
        pub_precision = "unknown"
        pub_source = "missing"

        # Try to parse from metadata
        published = raw.metadata.get("published")
        if published:
            try:
                dt = parsedate_to_datetime(published)
                pub_timestamp = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                pub_precision = "datetime"
                pub_source = "extracted"
            except (ValueError, TypeError):
                pass

        return TimestampResult(
            pub_timestamp=pub_timestamp,
            pub_precision=pub_precision,
            pub_source=pub_source,
        )

    def extract_canonical_refs(self, raw: RawEvent) -> dict:
        """Extract GAO report number from URL."""
        refs = {}

        match = GAO_REPORT_PATTERN.search(raw.url)
        if match:
            year, number = match.groups()
            refs["gao_report"] = f"GAO-{year}-{number}".upper()

        return refs
