"""Florida official sources - Florida DVA News."""

import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from src.state.common import RawSignal
from src.state.sources.base import StateSource

logger = logging.getLogger(__name__)

FL_DVA_NEWS_URL = "https://floridavets.org/news"


class FLOfficialSource(StateSource):
    """Fetches from Florida Department of Veterans Affairs."""

    def __init__(self, base_url: str = FL_DVA_NEWS_URL):
        self.base_url = base_url

    @property
    def source_id(self) -> str:
        return "fl_dva_news"

    @property
    def state(self) -> str:
        return "FL"

    def fetch(self) -> list[RawSignal]:
        """Fetch news from Florida DVA website."""
        try:
            response = httpx.get(self.base_url, timeout=30.0)
            response.raise_for_status()
            return self._parse_dva_news(response.text)
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            logger.error(f"Failed to fetch Florida DVA news: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching Florida DVA news: {e}")
            return []

    def _parse_dva_news(self, html: str) -> list[RawSignal]:
        """Parse Florida DVA news page HTML."""
        soup = BeautifulSoup(html, "html.parser")
        signals = []

        for article in soup.select(".news-entry, article, .post"):
            try:
                title_elem = article.select_one("h2 a, h3 a, .title a")
                if not title_elem:
                    continue

                title = title_elem.get_text(strip=True)
                href = title_elem.get("href", "")
                if not href:
                    continue

                url = urljoin("https://floridavets.org/", href)

                date_elem = article.select_one("time, .date, .pub-date")
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
        """Try to parse date from text like 'January 21, 2026'."""
        for fmt in ["%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%Y-%m-%d"]:
            try:
                dt = datetime.strptime(text.strip(), fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None
