"""Trade press source agent - veterans affairs publications."""

from datetime import UTC, datetime

import feedparser

from src.resilience.circuit_breaker import oversight_cb
from src.resilience.rate_limiter import external_api_limiter
from src.resilience.wiring import circuit_breaker_sync, with_timeout

from .base import OversightAgent, RawEvent, TimestampResult

# VA-focused trade publications
TRADE_FEEDS = {
    "military_times_veterans": "https://www.militarytimes.com/arc/outboundfeeds/rss/category/veterans/",
    "military_times_benefits": "https://www.militarytimes.com/arc/outboundfeeds/rss/category/pay-benefits/",
    "federal_news": "https://federalnewsnetwork.com/category/all-news/feed/",
    "stars_stripes": "https://www.stripes.com/rss/",
}


class TradePressAgent(OversightAgent):
    """Agent for fetching VA trade press coverage."""

    source_type = "trade_press"

    def __init__(self, feeds: dict = None):
        self.feeds = feeds or TRADE_FEEDS
        self.va_keywords = ["veterans affairs", "VA ", "DVA"]

    @with_timeout(45, name="trade_press_rss")
    @circuit_breaker_sync(oversight_cb)
    def _fetch_feed(self, feed_url: str):
        """Fetch and parse an RSS feed with resilience protection."""
        return feedparser.parse(feed_url)

    def _is_va_related(self, title: str, content: str) -> bool:
        """Check if content is VA-related."""
        combined = f"{title} {content}".lower()
        return any(kw.lower() in combined for kw in self.va_keywords)

    def fetch_new(self, since: datetime | None) -> list[RawEvent]:
        """Fetch new trade press stories."""
        events = []

        for source, feed_url in self.feeds.items():
            try:
                external_api_limiter.allow()
                feed = self._fetch_feed(feed_url)

                for entry in feed.entries:
                    title = entry.title
                    content = getattr(entry, "summary", "")

                    # Filter to VA-related content
                    if not self._is_va_related(title, content):
                        continue

                    pub_date = None
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        pub_date = datetime(*entry.published_parsed[:6], tzinfo=UTC)

                    if since and pub_date and pub_date < since:
                        continue

                    fetched_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

                    events.append(
                        RawEvent(
                            url=entry.link,
                            title=title,
                            raw_html=content,
                            fetched_at=fetched_at,
                            excerpt=content[:500] if content else None,
                            metadata={
                                "published": getattr(entry, "published", None),
                                "source": source,
                            },
                        )
                    )
            except Exception:
                continue

        return events

    def backfill(self, start: datetime, end: datetime) -> list[RawEvent]:
        """Backfill - RSS only has recent items."""
        return self.fetch_new(since=None)

    def extract_timestamps(self, raw: RawEvent) -> TimestampResult:
        """Extract timestamps from trade press story."""
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
        """Extract references from story."""
        refs = {}

        source = raw.metadata.get("source")
        if source:
            refs["outlet"] = source

        return refs
