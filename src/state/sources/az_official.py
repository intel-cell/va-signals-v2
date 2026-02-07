"""Arizona official sources - Department of Veterans' Services."""

import logging
from datetime import datetime
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from src.state.common import RawSignal
from src.state.sources.base import StateSource

logger = logging.getLogger(__name__)

# Arizona DVS (dvs.az.gov) returns 403 to automated requests
# AZ coverage comes from NewsAPI + RSS feeds (Google News, AZ Central)
AZ_DVS_PRESS_URL = "https://dvs.az.gov/press-releases"
AZ_DVS_DISABLED = True  # Site returns 403 as of 2026-02-05 — enable when accessible


class AZOfficialSource(StateSource):
    """Fetches from Arizona DVS press releases (static HTML, httpx+BS4).

    Currently disabled because dvs.az.gov returns 403 to automated
    requests. AZ coverage comes from NewsAPI and RSS feeds.
    Enable when site becomes accessible.
    """

    def __init__(self, base_url: str = AZ_DVS_PRESS_URL):
        self.base_url = base_url

    @property
    def source_id(self) -> str:
        return "az_dvs_news"

    @property
    def state(self) -> str:
        return "AZ"

    def fetch(self) -> list[RawSignal]:
        """Fetch press releases from Arizona DVS."""
        if AZ_DVS_DISABLED:
            logger.info("Arizona DVS source disabled (site returns 403)")
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
            logger.error(f"Failed to fetch Arizona DVS press releases: {e}")
            return []

    def _parse_press_releases(self, html: str) -> list[RawSignal]:
        """Parse Arizona DVS press releases page HTML."""
        soup = BeautifulSoup(html, "html.parser")
        signals = []

        # Drupal-based — try common selectors (will need tuning when accessible)
        selectors = [
            "article",
            ".views-row",
            ".node--type-press-release",
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
                title_elem = article.select_one(
                    "h2 a, h3 a, .field-content a"
                ) or article.select_one("a")
                if not title_elem:
                    continue

                title = title_elem.get_text(strip=True)
                if not title or len(title) < 5:
                    continue

                href = title_elem.get("href", "")
                if not href:
                    continue

                url = urljoin("https://dvs.az.gov/", href)

                # Date
                date_elem = article.select_one("time, .date, .field--name-created")
                pub_date = None
                if date_elem:
                    datetime_attr = date_elem.get("datetime")
                    if datetime_attr and len(datetime_attr) >= 10:
                        pub_date = datetime_attr[:10]
                    else:
                        pub_date = self._parse_date_text(date_elem.get_text())

                # Excerpt
                excerpt_elem = article.select_one("p, .excerpt, .field--name-body")
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
                logger.warning(f"Failed to parse Arizona DVS article: {e}")
                continue

        return signals

    def _parse_date_text(self, text: str) -> str | None:
        """Try to parse date from text."""
        for fmt in ["%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%m/%d/%Y"]:
            try:
                dt = datetime.strptime(text.strip(), fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None
