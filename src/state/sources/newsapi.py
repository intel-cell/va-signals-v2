"""NewsAPI.org news source for state-level veteran news."""

import logging
import subprocess
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from src.state.common import RawSignal
from src.state.sources.base import StateSource

logger = logging.getLogger(__name__)

NEWSAPI_BASE_URL = "https://newsapi.org/v2/everything"

SEARCH_QUERIES = {
    "TX": [
        "Texas veterans PACT Act",
        "Texas VA community care",
        "Texas Veterans Commission",
    ],
    "CA": [
        "California veterans PACT Act",
        "CalVet toxic exposure",
        "California VA community care",
    ],
    "FL": [
        "Florida veterans PACT Act",
        "Florida VA healthcare",
        "Florida veterans affairs",
    ],
}


def _get_newsapi_key() -> str:
    """Get NewsAPI key from Keychain."""
    result = subprocess.run(
        ["security", "find-generic-password", "-s", "newsapi-key", "-w"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError("Could not retrieve newsapi-key from Keychain")
    return result.stdout.strip()


class NewsAPISource(StateSource):
    """Fetches veteran news from NewsAPI.org for a specific state."""

    def __init__(self, state: str, lookback_days: int = 7):
        if state not in SEARCH_QUERIES:
            raise ValueError(f"Unknown state: {state}. Must be one of {list(SEARCH_QUERIES.keys())}")
        self._state = state
        self.lookback_days = lookback_days

    @property
    def source_id(self) -> str:
        return f"newsapi_{self._state.lower()}"

    @property
    def state(self) -> str:
        return self._state

    def fetch(self) -> list[RawSignal]:
        """Fetch news from NewsAPI for this state's search queries."""
        try:
            api_key = _get_newsapi_key()
            from_date = (datetime.now(timezone.utc) - timedelta(days=self.lookback_days)).strftime("%Y-%m-%d")

            all_signals = []
            seen_urls = set()

            for query in SEARCH_QUERIES[self._state]:
                try:
                    signals = self._search(api_key, query, from_date)
                    # Deduplicate by URL
                    for signal in signals:
                        if signal.url not in seen_urls:
                            seen_urls.add(signal.url)
                            all_signals.append(signal)
                except Exception as e:
                    logger.warning(f"NewsAPI query failed for '{query}': {e}")
                    continue

            return all_signals

        except Exception as e:
            logger.error(f"Failed to fetch NewsAPI news for {self._state}: {e}")
            return []

    def _search(self, api_key: str, query: str, from_date: str) -> list[RawSignal]:
        """Execute a single search query against NewsAPI."""
        response = httpx.get(
            NEWSAPI_BASE_URL,
            params={
                "q": query,
                "from": from_date,
                "sortBy": "publishedAt",
                "language": "en",
                "pageSize": 20,
            },
            headers={"X-Api-Key": api_key},
            timeout=30.0,
        )
        response.raise_for_status()

        data = response.json()
        if data.get("status") != "ok":
            raise ValueError(f"NewsAPI error: {data.get('message', 'Unknown error')}")

        signals = []
        for article in data.get("articles", []):
            try:
                pub_date = None
                if article.get("publishedAt"):
                    pub_date = article["publishedAt"][:10]  # YYYY-MM-DD

                signals.append(
                    RawSignal(
                        url=article["url"],
                        title=article["title"],
                        content=article.get("description"),
                        pub_date=pub_date,
                        source_id=self.source_id,
                        state=self._state,
                    )
                )
            except (KeyError, TypeError) as e:
                logger.warning(f"Failed to parse NewsAPI article: {e}")
                continue

        return signals
