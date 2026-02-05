"""Ohio official sources - Department of Veterans Services."""

import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from src.state.common import RawSignal
from src.state.sources.base import StateSource

logger = logging.getLogger(__name__)

# Ohio DVS site (dvs.ohio.gov) is currently returning 404 errors
# OH coverage primarily comes from NewsAPI + RSS feeds (Google News, Columbus Dispatch)
ODVS_NEWS_URL = "https://dvs.ohio.gov/news-and-events"
ODVS_DISABLED = True  # Site unreachable as of 2026-02-05 — enable when accessible


class OHOfficialSource(StateSource):
    """Fetches from Ohio DVS news page (static HTML, httpx+BS4).

    Currently disabled because dvs.ohio.gov returns 404. OH coverage
    comes from NewsAPI and RSS feeds. Enable when site becomes accessible.
    """

    def __init__(self, base_url: str = ODVS_NEWS_URL):
        self.base_url = base_url

    @property
    def source_id(self) -> str:
        return "oh_odvs_news"

    @property
    def state(self) -> str:
        return "OH"

    def fetch(self) -> list[RawSignal]:
        """Fetch news from Ohio DVS website."""
        if ODVS_DISABLED:
            logger.info("Ohio DVS source disabled (site returning 404)")
            return []

        try:
            response = httpx.get(
                self.base_url,
                timeout=30.0,
                follow_redirects=True,
                headers={
                    "User-Agent": "VA-Signals-Monitor/2.0 (veteran-advocacy; +https://github.com/vetclaims)"
                },
            )
            response.raise_for_status()
            return self._parse_odvs_news(response.text)
        except Exception as e:
            logger.error(f"Failed to fetch Ohio DVS news: {e}")
            return []

    def _parse_odvs_news(self, html: str) -> list[RawSignal]:
        """Parse Ohio DVS news page HTML."""
        soup = BeautifulSoup(html, "html.parser")
        signals = []

        # Try multiple selectors — will need tuning when site comes back online
        selectors = [
            "article",
            ".news-item",
            ".post",
            ".view-content .views-row",  # Drupal views
            ".news-entry",
        ]

        articles = []
        for selector in selectors:
            articles = soup.select(selector)
            if articles:
                logger.debug(f"Found {len(articles)} articles with selector: {selector}")
                break

        for article in articles:
            try:
                title_elem = (
                    article.select_one("h3 a, h2 a, .title a")
                    or article.select_one("a[href*='news']")
                    or article.select_one("a")
                )
                if not title_elem:
                    continue

                title = title_elem.get_text(strip=True)
                if not title or len(title) < 5:
                    continue

                href = title_elem.get("href", "")
                if not href:
                    continue

                url = urljoin("https://dvs.ohio.gov/", href)

                # Try to find date
                date_elem = article.select_one(".date, time, .pub-date, .field--name-created")
                pub_date = None
                if date_elem:
                    datetime_attr = date_elem.get("datetime")
                    if datetime_attr and len(datetime_attr) >= 10:
                        pub_date = datetime_attr[:10]
                    else:
                        pub_date = self._parse_date_text(date_elem.get_text())

                # Try to find excerpt
                excerpt_elem = article.select_one("p, .excerpt, .summary, .field--name-body")
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
                logger.warning(f"Failed to parse Ohio DVS article: {e}")
                continue

        return signals

    def _parse_date_text(self, text: str) -> Optional[str]:
        """Try to parse date from text."""
        for fmt in ["%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%m/%d/%Y"]:
            try:
                dt = datetime.strptime(text.strip(), fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None
