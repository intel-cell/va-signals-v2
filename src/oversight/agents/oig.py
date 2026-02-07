"""VA Office of Inspector General (OIG) source agent."""

import re
from datetime import UTC, datetime

import feedparser

from src.resilience.circuit_breaker import oversight_cb
from src.resilience.rate_limiter import external_api_limiter
from src.resilience.wiring import circuit_breaker_sync, with_timeout

from .base import OversightAgent, RawEvent, TimestampResult

OIG_RSS_URL = "https://www.vaoig.gov/rss.xml"
OIG_REPORT_PATTERN = re.compile(r"(\d{2})-(\d{5})-(\d+)", re.IGNORECASE)


class OIGAgent(OversightAgent):
    """Agent for fetching VA OIG reports."""

    source_type = "oig"

    def __init__(self, rss_url: str = OIG_RSS_URL):
        self.rss_url = rss_url

    @with_timeout(45, name="oig_rss")
    @circuit_breaker_sync(oversight_cb)
    def _fetch_feed(self):
        """Fetch and parse the OIG RSS feed with resilience protection."""
        return feedparser.parse(self.rss_url)

    def fetch_new(self, since: datetime | None) -> list[RawEvent]:
        """Fetch new OIG reports from RSS feed."""
        external_api_limiter.allow()
        feed = self._fetch_feed()
        events = []

        for entry in feed.entries:
            pub_date = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                pub_date = datetime(*entry.published_parsed[:6], tzinfo=UTC)

            if since and pub_date and pub_date < since:
                continue

            fetched_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

            events.append(
                RawEvent(
                    url=entry.link,
                    title=entry.title,
                    raw_html=getattr(entry, "summary", ""),
                    fetched_at=fetched_at,
                    excerpt=getattr(entry, "summary", "")[:500]
                    if hasattr(entry, "summary")
                    else None,
                    metadata={
                        "published": getattr(entry, "published", None),
                    },
                )
            )

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
        """Extract timestamps from OIG report."""
        pub_timestamp = None
        pub_precision = "unknown"
        pub_source = "missing"

        published = raw.metadata.get("published")
        if published:
            try:
                # Try parsing RSS date format
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
        """Extract OIG report number from URL/title."""
        refs = {}
        combined = f"{raw.url} {raw.title}"

        match = OIG_REPORT_PATTERN.search(combined)
        if match:
            refs["oig_report"] = "-".join(match.groups())

        return refs
