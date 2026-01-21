"""Committee Press Release source agent."""

import re
from datetime import datetime, timezone
from typing import Optional

import feedparser

from .base import OversightAgent, RawEvent, TimestampResult


# VA-related committee RSS feeds
COMMITTEE_FEEDS = {
    "hvac": "https://veterans.house.gov/rss.xml",  # House Veterans Affairs
    "svac": "https://www.veterans.senate.gov/rss/feeds/pressreleases.xml",  # Senate Veterans Affairs
}


class CommitteePressAgent(OversightAgent):
    """Agent for fetching VA committee press releases."""

    source_type = "committee_press"

    def __init__(self, feeds: dict = None):
        self.feeds = feeds or COMMITTEE_FEEDS

    def fetch_new(self, since: Optional[datetime]) -> list[RawEvent]:
        """Fetch new press releases from committee feeds."""
        events = []

        for committee, feed_url in self.feeds.items():
            try:
                feed = feedparser.parse(feed_url)

                for entry in feed.entries:
                    pub_date = None
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

                    if since and pub_date and pub_date < since:
                        continue

                    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

                    events.append(
                        RawEvent(
                            url=entry.link,
                            title=entry.title,
                            raw_html=getattr(entry, "summary", ""),
                            fetched_at=fetched_at,
                            excerpt=getattr(entry, "summary", "")[:500],
                            metadata={
                                "published": getattr(entry, "published", None),
                                "committee": committee,
                            },
                        )
                    )
            except Exception:
                # Skip failed feeds
                continue

        return events

    def backfill(self, start: datetime, end: datetime) -> list[RawEvent]:
        """Backfill - RSS only has recent items."""
        all_events = self.fetch_new(since=None)
        return [e for e in all_events if self._in_range(e, start, end)]

    def _in_range(self, event: RawEvent, start: datetime, end: datetime) -> bool:
        ts = self.extract_timestamps(event)
        if ts.pub_timestamp:
            try:
                pub_dt = datetime.fromisoformat(ts.pub_timestamp.replace("Z", "+00:00"))
                return start <= pub_dt <= end
            except ValueError:
                pass
        return False

    def extract_timestamps(self, raw: RawEvent) -> TimestampResult:
        """Extract timestamps from press release."""
        pub_timestamp = None
        pub_precision = "unknown"
        pub_source = "missing"

        published = raw.metadata.get("published")
        if published:
            try:
                from email.utils import parsedate_to_datetime
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
        """Extract press release reference."""
        refs = {}

        committee = raw.metadata.get("committee")
        if committee:
            refs["committee"] = committee

        return refs
