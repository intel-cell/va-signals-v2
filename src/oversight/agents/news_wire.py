"""News Wire source agent - NewsAPI integration for VA-related news."""

import logging
import re
from datetime import UTC, datetime, timedelta

import httpx

from src.resilience.circuit_breaker import newsapi_cb
from src.resilience.rate_limiter import external_api_limiter
from src.resilience.wiring import circuit_breaker_sync, with_timeout
from src.secrets import get_env_or_keychain

from .base import OversightAgent, RawEvent, TimestampResult

logger = logging.getLogger(__name__)

NEWSAPI_BASE_URL = "https://newsapi.org/v2/everything"

# VA-specific search terms for national news coverage
VA_SEARCH_TERMS = [
    "veterans affairs",
    "VA hospital",
    "VA benefits",
    "VA secretary",
    "Department of Veterans Affairs",
]

# Default lookback for fetch_new when no since date provided
DEFAULT_LOOKBACK_DAYS = 7


def _get_newsapi_key() -> str:
    """Get NewsAPI key from environment or Keychain."""
    return get_env_or_keychain("NEWSAPI_KEY", "newsapi-key")


class NewsWireAgent(OversightAgent):
    """Agent for fetching VA-related news wire stories from NewsAPI."""

    source_type = "news_wire"

    def __init__(self, lookback_days: int = DEFAULT_LOOKBACK_DAYS):
        self.search_terms = VA_SEARCH_TERMS
        self.lookback_days = lookback_days

    @with_timeout(45, name="newsapi")
    @circuit_breaker_sync(newsapi_cb)
    def _fetch_newsapi(self, params: dict, api_key: str) -> httpx.Response:
        """Fetch from NewsAPI with resilience protection."""
        return httpx.get(
            NEWSAPI_BASE_URL,
            params=params,
            headers={"X-Api-Key": api_key},
            timeout=30.0,
        )

    def fetch_new(self, since: datetime | None) -> list[RawEvent]:
        """
        Fetch new news wire stories from NewsAPI.

        Args:
            since: Datetime of last successful fetch, or None for default lookback

        Returns:
            List of RawEvent objects for VA-related news
        """
        try:
            api_key = _get_newsapi_key()
        except Exception as e:
            logger.error(f"Failed to get NewsAPI key: {e}")
            return []

        # Determine from_date based on since parameter
        if since:
            from_date = since.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            from_date = (datetime.now(UTC) - timedelta(days=self.lookback_days)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )

        all_events = []
        seen_urls: set[str] = set()

        for query in self.search_terms:
            try:
                events = self._search(api_key, query, from_date)
                # Deduplicate by URL
                for event in events:
                    if event.url not in seen_urls:
                        seen_urls.add(event.url)
                        all_events.append(event)
            except Exception as e:
                logger.warning(f"NewsAPI query failed for '{query}': {e}")
                continue

        logger.info(f"NewsWireAgent fetched {len(all_events)} unique articles")
        return all_events

    def backfill(self, start: datetime, end: datetime) -> list[RawEvent]:
        """
        Backfill historical stories within date range.

        Args:
            start: Start of backfill window
            end: End of backfill window

        Returns:
            List of RawEvent objects within the date range
        """
        try:
            api_key = _get_newsapi_key()
        except Exception as e:
            logger.error(f"Failed to get NewsAPI key: {e}")
            return []

        from_date = start.strftime("%Y-%m-%dT%H:%M:%SZ")
        to_date = end.strftime("%Y-%m-%dT%H:%M:%SZ")

        all_events = []
        seen_urls: set[str] = set()

        for query in self.search_terms:
            try:
                events = self._search(api_key, query, from_date, to_date)
                for event in events:
                    if event.url not in seen_urls:
                        seen_urls.add(event.url)
                        all_events.append(event)
            except Exception as e:
                logger.warning(f"NewsAPI backfill query failed for '{query}': {e}")
                continue

        # Filter to ensure events fall within the exact date range
        filtered_events = []
        for event in all_events:
            ts = self.extract_timestamps(event)
            if ts.pub_timestamp:
                try:
                    pub_dt = datetime.fromisoformat(ts.pub_timestamp.replace("Z", "+00:00"))
                    if start <= pub_dt <= end:
                        filtered_events.append(event)
                except (ValueError, TypeError):
                    # Include if we can't parse the date
                    filtered_events.append(event)
            else:
                # Include if no publish date available
                filtered_events.append(event)

        logger.info(f"NewsWireAgent backfilled {len(filtered_events)} articles")
        return filtered_events

    def _search(
        self,
        api_key: str,
        query: str,
        from_date: str,
        to_date: str | None = None,
    ) -> list[RawEvent]:
        """
        Execute a single search query against NewsAPI.

        Args:
            api_key: NewsAPI key
            query: Search query string
            from_date: Start date (ISO format)
            to_date: Optional end date (ISO format)

        Returns:
            List of RawEvent objects
        """
        params = {
            "q": query,
            "from": from_date,
            "sortBy": "publishedAt",
            "language": "en",
            "pageSize": 50,  # Max allowed by NewsAPI free tier
        }
        if to_date:
            params["to"] = to_date

        external_api_limiter.allow()
        response = self._fetch_newsapi(params, api_key)
        response.raise_for_status()

        data = response.json()
        if data.get("status") != "ok":
            raise ValueError(f"NewsAPI error: {data.get('message', 'Unknown error')}")

        events = []
        fetched_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        for article in data.get("articles", []):
            try:
                # Extract source name
                source_name = None
                if article.get("source"):
                    source_name = article["source"].get("name")

                # Build content from available fields
                content = article.get("content") or article.get("description") or ""

                # Truncate description for excerpt
                description = article.get("description") or ""
                excerpt = description[:500] if description else None

                events.append(
                    RawEvent(
                        url=article["url"],
                        title=article.get("title") or "Untitled",
                        raw_html=content,
                        fetched_at=fetched_at,
                        excerpt=excerpt,
                        metadata={
                            "published": article.get("publishedAt"),
                            "source": source_name,
                            "author": article.get("author"),
                        },
                    )
                )
            except (KeyError, TypeError) as e:
                logger.warning(f"Failed to parse NewsAPI article: {e}")
                continue

        return events

    def extract_timestamps(self, raw: RawEvent) -> TimestampResult:
        """
        Extract timestamps from news story.

        Args:
            raw: Raw event to extract timestamps from

        Returns:
            TimestampResult with publication timestamp
        """
        published = raw.metadata.get("published")

        if published:
            # NewsAPI returns ISO 8601 format, normalize to UTC format
            try:
                # Parse and re-format to ensure consistent format
                dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
                pub_timestamp = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                return TimestampResult(
                    pub_timestamp=pub_timestamp,
                    pub_precision="datetime",
                    pub_source="extracted",
                )
            except (ValueError, TypeError):
                # Return raw value if parsing fails
                return TimestampResult(
                    pub_timestamp=published,
                    pub_precision="datetime",
                    pub_source="extracted",
                )

        return TimestampResult(
            pub_timestamp=None,
            pub_precision="unknown",
            pub_source="missing",
        )

    def extract_canonical_refs(self, raw: RawEvent) -> dict:
        """
        Extract references from news story for deduplication.

        Args:
            raw: Raw event

        Returns:
            Dict of canonical references (bill numbers, etc.)
        """
        refs = {}

        # Look for bill references in story content
        text = f"{raw.title} {raw.raw_html}"
        bill_pattern = re.compile(r"(H\.?R\.?\s*\d+|S\.?\s*\d+)", re.IGNORECASE)
        match = bill_pattern.search(text)
        if match:
            refs["bill_mentioned"] = match.group(1)

        # Add source as a reference for tracking
        source = raw.metadata.get("source")
        if source:
            refs["news_source"] = source

        return refs
