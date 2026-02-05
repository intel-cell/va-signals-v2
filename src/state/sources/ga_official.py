"""Georgia official sources - GDVS Press Releases."""

import logging
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from src.state.common import RawSignal
from src.state.sources.base import StateSource

logger = logging.getLogger(__name__)

GDVS_PRESS_URL = "https://veterans.georgia.gov/press-releases"
GDVS_BASE_URL = "https://veterans.georgia.gov"


class GAOfficialSource(StateSource):
    """Fetches from GA DVS press releases (static HTML, httpx+BS4).

    GovHub Drupal theme. Articles are div.news-teaser containing
    a[href*="/press-releases/"] with title + date concatenated in link text.
    Dates extractable from URL pattern: /press-releases/YYYY-MM-DD/slug.
    """

    def __init__(self, base_url: str = GDVS_PRESS_URL, max_pages: int = 2):
        self.base_url = base_url
        self.max_pages = max_pages

    @property
    def source_id(self) -> str:
        return "ga_dvs_news"

    @property
    def state(self) -> str:
        return "GA"

    def fetch(self) -> list[RawSignal]:
        """Fetch press releases from GA DVS (paginated)."""
        all_signals = []
        seen_urls: set[str] = set()

        for page in range(self.max_pages):
            try:
                url = self.base_url if page == 0 else f"{self.base_url}?page={page}"
                response = httpx.get(
                    url,
                    timeout=30.0,
                    follow_redirects=True,
                    headers={
                        "User-Agent": "VA-Signals-Monitor/2.0 (veteran-advocacy; +https://github.com/vetclaims)"
                    },
                )
                response.raise_for_status()

                signals = self._parse_press_releases(response.text)
                if not signals:
                    break

                for sig in signals:
                    if sig.url not in seen_urls:
                        seen_urls.add(sig.url)
                        all_signals.append(sig)

            except Exception as e:
                logger.error(f"Failed to fetch GA DVS press releases page {page}: {e}")
                break

        return all_signals

    def _parse_press_releases(self, html: str) -> list[RawSignal]:
        """Parse GA DVS press releases page.

        Structure: a[href*="/press-releases/YYYY-MM-DD/"] inside div.news-teaser.
        Title and date are concatenated in the link text (e.g.,
        "Georgia Department Opens Applications...January 13, 2026").
        Date also extractable from URL path.
        """
        soup = BeautifulSoup(html, "html.parser")
        signals = []

        # Select article links (exclude nav links to /press-releases itself)
        links = soup.select('a[href*="/press-releases/"]')
        article_links = [a for a in links if re.search(r"/press-releases/\d{4}", a.get("href", ""))]

        if not article_links:
            logger.warning("No GA DVS press release articles found")
            return []

        logger.debug(f"Found {len(article_links)} GA DVS press release links")

        for link in article_links:
            try:
                href = link.get("href", "")
                if not href:
                    continue

                url = urljoin(GDVS_BASE_URL, href)

                # Extract date from URL pattern: /press-releases/YYYY-MM-DD/slug
                pub_date = None
                date_match = re.search(r"/press-releases/(\d{4}-\d{2}-\d{2})/", href)
                if date_match:
                    pub_date = date_match.group(1)

                # Extract title — strip trailing date from concatenated text
                raw_text = link.get_text(strip=True)
                title = self._extract_title(raw_text)

                if not title or len(title) < 5:
                    continue

                signals.append(
                    RawSignal(
                        url=url,
                        title=title,
                        content=None,
                        pub_date=pub_date,
                        source_id=self.source_id,
                        state=self.state,
                    )
                )

            except (AttributeError, ValueError, TypeError) as e:
                logger.warning(f"Failed to parse GA DVS article: {e}")
                continue

        return signals

    def _extract_title(self, text: str) -> str:
        """Extract title from concatenated title+date text.

        GA format: "Title TextMonth DD, YYYY" (no separator).
        We strip the trailing date pattern.
        """
        # Try to find and remove trailing date
        match = re.search(
            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\s*$",
            text,
        )
        if match:
            return text[: match.start()].strip()
        return text.strip()
