"""RSS feed aggregator for state-level veteran news."""

import logging
from datetime import datetime
from typing import TypedDict
from time import mktime

import feedparser

from src.state.common import RawSignal, is_veteran_relevant
from src.state.sources.base import StateSource

logger = logging.getLogger(__name__)


class FeedInfo(TypedDict):
    name: str
    url: str


RSS_FEEDS: dict[str, list[FeedInfo]] = {
    "TX": [
        {
            "name": "Texas Tribune",
            "url": "https://www.texastribune.org/feed/",
        },
        {
            "name": "Google News Texas Veterans",
            "url": "https://news.google.com/rss/search?q=Texas+veterans&hl=en-US&gl=US&ceid=US:en",
        },
    ],
    "CA": [
        {
            "name": "CalVet Connect Blog",
            "url": "https://calvetconnect.blog/feed/",
        },
        {
            "name": "CalMatters",
            "url": "https://calmatters.org/feed/",
        },
        {
            "name": "LA Times",
            "url": "https://www.latimes.com/politics/rss2.0.xml",
        },
        {
            "name": "Google News California Veterans",
            "url": "https://news.google.com/rss/search?q=California+veterans+CalVet&hl=en-US&gl=US&ceid=US:en",
        },
    ],
    "FL": [
        {
            "name": "Florida Phoenix",
            "url": "https://floridaphoenix.com/feed/",
        },
        {
            "name": "Tampa Bay Times",
            "url": "https://www.tampabay.com/arcio/rss/category/news-politics-state/",
        },
    ],
    "PA": [
        {
            "name": "PennLive",
            "url": "https://www.pennlive.com/arc/outboundfeeds/rss/?outputType=xml",
        },
        {
            "name": "Google News PA Veterans",
            "url": "https://news.google.com/rss/search?q=Pennsylvania+veterans&hl=en-US&gl=US&ceid=US:en",
        },
    ],
    "OH": [
        {
            "name": "Columbus Dispatch",
            "url": "https://www.dispatch.com/arcio/rss/category/news/",
        },
        {
            "name": "Google News OH Veterans",
            "url": "https://news.google.com/rss/search?q=Ohio+veterans&hl=en-US&gl=US&ceid=US:en",
        },
    ],
    "NY": [
        {
            "name": "Times Union Albany",
            "url": "https://www.timesunion.com/news/rss/feed/",
        },
        {
            "name": "Google News NY Veterans",
            "url": "https://news.google.com/rss/search?q=New+York+veterans&hl=en-US&gl=US&ceid=US:en",
        },
    ],
}


class RSSSource(StateSource):
    """Aggregates veteran news from RSS feeds for a specific state."""

    def __init__(self, state: str):
        if state not in RSS_FEEDS:
            raise ValueError(f"Unknown state: {state}. Must be one of {list(RSS_FEEDS.keys())}")
        self._state = state

    @property
    def source_id(self) -> str:
        return f"rss_{self._state.lower()}"

    @property
    def state(self) -> str:
        return self._state

    def fetch(self) -> list[RawSignal]:
        """Fetch news from all RSS feeds for this state."""
        all_signals = []
        seen_urls: set[str] = set()

        for feed_info in RSS_FEEDS[self._state]:
            signals = self._parse_feed(feed_info)
            for signal in signals:
                if signal.url not in seen_urls:
                    seen_urls.add(signal.url)
                    all_signals.append(signal)

        return all_signals

    def _parse_feed(self, feed_info: FeedInfo) -> list[RawSignal]:
        """Parse a single RSS feed and filter for veteran relevance."""
        feed = feedparser.parse(feed_info["url"])
        if feed.bozo:
            logger.warning(f"Feed parse error for {feed_info['name']}: {getattr(feed, 'bozo_exception', 'unknown error')}")
            return []
        signals = []

        for entry in feed.entries:
            try:
                title = entry.get("title", "")
                summary = entry.get("summary", "")

                # Filter: only include veteran-relevant articles
                if not is_veteran_relevant(f"{title} {summary}"):
                    continue

                url = entry.get("link", "")
                if not url:
                    continue

                # Parse publication date
                pub_date = None
                if entry.get("published_parsed"):
                    try:
                        dt = datetime.fromtimestamp(mktime(entry.published_parsed))
                        pub_date = dt.strftime("%Y-%m-%d")
                    except (TypeError, ValueError):
                        pass

                signals.append(
                    RawSignal(
                        url=url,
                        title=title,
                        content=summary,
                        pub_date=pub_date,
                        source_id=self.source_id,
                        state=self._state,
                    )
                )

            except (AttributeError, KeyError) as e:
                logger.warning(f"Failed to parse RSS entry: {e}")
                continue

        return signals
