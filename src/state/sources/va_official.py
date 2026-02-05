"""Virginia official sources - Department of Veterans Services."""

import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from src.state.common import RawSignal
from src.state.sources.base import StateSource

logger = logging.getLogger(__name__)

# Virginia DVS (dvs.virginia.gov) returns 403 to automated requests
# VA state coverage comes from NewsAPI + RSS feeds (Google News, Richmond Times-Dispatch)
VA_DVS_PRESS_URL = "https://www.dvs.virginia.gov/news-room/press-release"
VA_DVS_DISABLED = True  # Site returns 403 as of 2026-02-05 — enable when accessible


class VAOfficialSource(StateSource):
    """Fetches from Virginia DVS press releases (static HTML, httpx+BS4).

    Currently disabled because dvs.virginia.gov returns 403 to automated
    requests. VA state coverage comes from NewsAPI and RSS feeds.
    Enable when site becomes accessible.
    """

    def __init__(self, base_url: str = VA_DVS_PRESS_URL):
        self.base_url = base_url

    @property
    def source_id(self) -> str:
        return "va_dvs_news"

    @property
    def state(self) -> str:
        return "VA"

    def fetch(self) -> list[RawSignal]:
        """Fetch press releases from Virginia DVS."""
        if VA_DVS_DISABLED:
            logger.info("Virginia DVS source disabled (site returns 403)")
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
            return self._parse_press_releases(response.text)
        except Exception as e:
            logger.error(f"Failed to fetch Virginia DVS press releases: {e}")
            return []

    def _parse_press_releases(self, html: str) -> list[RawSignal]:
        """Parse Virginia DVS press releases page HTML."""
        soup = BeautifulSoup(html, "html.parser")
        signals = []

        # WordPress-based — try common selectors (will need tuning when accessible)
        selectors = [
            "article",
            ".post",
            ".entry",
            ".press-release",
            "h2 a",
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
                    article.select_one("h2 a, h3 a, .entry-title a")
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

                url = urljoin("https://www.dvs.virginia.gov/", href)

                # Date
                date_elem = article.select_one("time, .date, .published, .entry-date")
                pub_date = None
                if date_elem:
                    datetime_attr = date_elem.get("datetime")
                    if datetime_attr and len(datetime_attr) >= 10:
                        pub_date = datetime_attr[:10]
                    else:
                        pub_date = self._parse_date_text(date_elem.get_text())

                # Excerpt
                excerpt_elem = article.select_one("p, .excerpt, .entry-content p")
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
                logger.warning(f"Failed to parse Virginia DVS article: {e}")
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
