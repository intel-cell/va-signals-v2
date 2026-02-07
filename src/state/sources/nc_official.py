"""North Carolina official sources - NCDMVA Press Releases."""

import logging
from datetime import datetime
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from src.state.common import RawSignal
from src.state.sources.base import StateSource

logger = logging.getLogger(__name__)

NCDMVA_PRESS_URL = "https://www.milvets.nc.gov/news/press-releases"
NCDMVA_BASE_URL = "https://www.milvets.nc.gov"


class NCOfficialSource(StateSource):
    """Fetches from NC DMVA press releases (static HTML, httpx+BS4).

    Drupal-based site with .views-row containers, h2 a titles,
    and <time datetime="..."> date elements. Pagination via ?page=N.
    """

    def __init__(self, base_url: str = NCDMVA_PRESS_URL, max_pages: int = 2):
        self.base_url = base_url
        self.max_pages = max_pages

    @property
    def source_id(self) -> str:
        return "nc_dmva_news"

    @property
    def state(self) -> str:
        return "NC"

    def fetch(self) -> list[RawSignal]:
        """Fetch press releases from NC DMVA (paginated)."""
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
                logger.error(f"Failed to fetch NC DMVA press releases page {page}: {e}")
                break

        return all_signals

    def _parse_press_releases(self, html: str) -> list[RawSignal]:
        """Parse NC DMVA press releases page.

        Structure: .views-row containing h2 > a (title) and time[datetime] (date).
        """
        soup = BeautifulSoup(html, "html.parser")
        signals = []

        rows = soup.select(".views-row")
        if not rows:
            rows = soup.select(".view-content article, .view-content .node")

        if not rows:
            logger.warning("No NC DMVA press release rows found")
            return []

        logger.debug(f"Found {len(rows)} NC DMVA press release rows")

        for row in rows:
            try:
                # Title from h2 > a
                title_link = row.select_one("h2 a, h3 a, .field-content a")
                if not title_link:
                    continue

                title = title_link.get_text(strip=True)
                if not title or len(title) < 5:
                    continue

                href = title_link.get("href", "")
                if not href:
                    continue

                url = urljoin(NCDMVA_BASE_URL, href)

                # Date from <time datetime="...">
                pub_date = None
                time_elem = row.select_one("time[datetime]")
                if time_elem:
                    datetime_attr = time_elem.get("datetime", "")
                    if datetime_attr and len(datetime_attr) >= 10:
                        pub_date = datetime_attr[:10]
                    else:
                        pub_date = self._parse_date_text(time_elem.get_text())

                # Excerpt from paragraph
                content = None
                for p in row.find_all("p"):
                    text = p.get_text(strip=True)
                    if text and len(text) > 20 and text != title:
                        content = text[:500]
                        break

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
                logger.warning(f"Failed to parse NC DMVA article: {e}")
                continue

        return signals

    def _parse_date_text(self, text: str) -> str | None:
        """Try to parse date from text like 'Thursday, January 29, 2026'."""
        import re

        # Strip day-of-week prefix
        cleaned = re.sub(
            r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s*", "", text.strip()
        )
        for fmt in ["%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%m/%d/%Y"]:
            try:
                dt = datetime.strptime(cleaned.strip(), fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None
