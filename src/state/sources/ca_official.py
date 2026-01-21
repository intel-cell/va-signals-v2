"""California official sources - CalVet Newsroom."""

import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from src.state.common import RawSignal
from src.state.sources.base import StateSource

logger = logging.getLogger(__name__)

CALVET_NEWS_URL = "https://www.calvet.ca.gov/news"


class CAOfficialSource(StateSource):
    """Fetches from CalVet Newsroom."""

    def __init__(self, base_url: str = CALVET_NEWS_URL):
        self.base_url = base_url

    @property
    def source_id(self) -> str:
        return "ca_calvet_news"

    @property
    def state(self) -> str:
        return "CA"

    def fetch(self) -> list[RawSignal]:
        """Fetch news from CalVet website."""
        try:
            response = httpx.get(self.base_url, timeout=30.0)
            response.raise_for_status()
            return self._parse_calvet_news(response.text)
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            logger.error(f"Failed to fetch CalVet news: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching CalVet news: {e}")
            return []

    def _parse_calvet_news(self, html: str) -> list[RawSignal]:
        """Parse CalVet news page HTML."""
        soup = BeautifulSoup(html, "html.parser")
        signals = []

        for article in soup.select(".news-article, article, .post"):
            try:
                title_elem = article.select_one("h3 a, h2 a, .title a")
                if not title_elem:
                    continue

                title = title_elem.get_text(strip=True)
                href = title_elem.get("href", "")
                if not href:
                    continue

                url = urljoin("https://calvet.ca.gov/", href)

                date_elem = article.select_one(".date, time, .pub-date")
                pub_date = None
                if date_elem:
                    datetime_attr = date_elem.get("datetime")
                    if datetime_attr and len(datetime_attr) >= 10:
                        pub_date = datetime_attr[:10]
                    else:
                        pub_date = self._parse_date_text(date_elem.get_text())

                excerpt_elem = article.select_one("p, .excerpt, .summary")
                content = excerpt_elem.get_text(strip=True) if excerpt_elem else None

                signals.append(
                    RawSignal(
                        url=url,
                        title=title,
                        content=content,
                        pub_date=pub_date,
                        source_id=self.source_id,
                        state=self.state,
                    )
                )

            except (AttributeError, ValueError, TypeError) as e:
                logger.warning(f"Failed to parse article: {e}")
                continue

        return signals

    def _parse_date_text(self, text: str) -> Optional[str]:
        """Try to parse date from text like '01/19/2026'."""
        for fmt in ["%m/%d/%Y", "%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"]:
            try:
                dt = datetime.strptime(text.strip(), fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None
