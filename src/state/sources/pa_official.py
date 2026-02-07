"""Pennsylvania official sources - DMVA Newsroom."""

import logging
from datetime import datetime
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from src.state.common import RawSignal
from src.state.sources.base import StateSource

logger = logging.getLogger(__name__)

# PA DMVA moved from dmva.pa.gov to pa.gov/agencies/dmva/ in 2025
DMVA_NEWS_URL = "https://www.pa.gov/agencies/dmva/"
DMVA_BASE_URL = "https://www.pa.gov"


class PAOfficialSource(StateSource):
    """Fetches from PA DMVA press releases (static HTML, httpx+BS4)."""

    def __init__(self, base_url: str = DMVA_NEWS_URL):
        self.base_url = base_url

    @property
    def source_id(self) -> str:
        return "pa_dmva_news"

    @property
    def state(self) -> str:
        return "PA"

    def fetch(self) -> list[RawSignal]:
        """Fetch press releases from PA DMVA website."""
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
            return self._parse_dmva_news(response.text)
        except Exception as e:
            logger.error(f"Failed to fetch PA DMVA news: {e}")
            return []

    def _parse_dmva_news(self, html: str) -> list[RawSignal]:
        """Parse PA DMVA page for press releases.

        The DMVA page has a 'Press Releases' section with links in the pattern:
        /agencies/dmva/about-dmva/newsroom/{slug}
        """
        soup = BeautifulSoup(html, "html.parser")
        signals = []

        # Find all links to newsroom articles
        newsroom_links = soup.select('a[href*="/agencies/dmva/about-dmva/newsroom/"]')
        if not newsroom_links:
            # Fallback: try broader selectors
            newsroom_links = soup.select('a[href*="/dmva/"][href*="newsroom"]')

        if not newsroom_links:
            logger.warning("No PA DMVA newsroom links found")
            return []

        logger.debug(f"Found {len(newsroom_links)} PA DMVA newsroom links")

        seen_urls = set()
        for link in newsroom_links:
            try:
                href = link.get("href", "")
                if not href or href.endswith("/newsroom/") or href.endswith("/newsroom"):
                    continue

                url = urljoin(DMVA_BASE_URL, href)
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                raw_text = link.get_text(strip=True)
                if not raw_text or len(raw_text) < 10:
                    continue

                # PA press releases often have date prefix in link text
                # e.g., "January 16, 2026 - ICYMI: Pennsylvania National Guard..."
                title, pub_date = self._extract_date_and_title(raw_text)

                if not title or len(title) < 5:
                    continue

                # Try to find excerpt from parent/sibling elements
                content = None
                parent = link.find_parent("li") or link.find_parent("div")
                if parent:
                    # Look for a paragraph that isn't the link itself
                    para = parent.find("p")
                    if para and para != link:
                        content = para.get_text(strip=True)

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
                logger.warning(f"Failed to parse PA DMVA article: {e}")
                continue

        return signals

    def _extract_date_and_title(self, text: str) -> tuple[str, str | None]:
        """Extract date prefix and title from link text.

        PA DMVA formats observed:
        - 'January 16, 2026 - Title Here'         (dash separator)
        - 'January 16, 2026Title Here'             (no separator, date runs into title)
        - 'December 18, 2025Shapiro Administration...'
        - 'Title Here'                              (no date)
        """
        import re

        # Try common date-title separator patterns first
        for sep in [" - ", " – ", " — ", ": "]:
            if sep in text:
                parts = text.split(sep, 1)
                date_str = self._parse_date_text(parts[0].strip())
                if date_str:
                    return parts[1].strip(), date_str

        # Try regex for date directly concatenated with title (no separator)
        # Pattern: "Month DD, YYYY" immediately followed by title text
        match = re.match(
            r"((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})\s*(.*)",
            text,
        )
        if match:
            date_str = self._parse_date_text(match.group(1))
            title = match.group(2).strip()
            if date_str and title:
                return title, date_str

        # No date prefix found, treat entire text as title
        return text, None

    def _parse_date_text(self, text: str) -> str | None:
        """Try to parse date from text."""
        for fmt in ["%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%m/%d/%Y"]:
            try:
                dt = datetime.strptime(text.strip(), fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None
