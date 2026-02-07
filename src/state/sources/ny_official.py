"""New York official sources - Division of Veterans' Services Pressroom."""

import logging
from datetime import datetime
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from src.state.common import RawSignal
from src.state.sources.base import StateSource

logger = logging.getLogger(__name__)

NY_DVS_PRESSROOM_URL = "https://veterans.ny.gov/pressroom"
NY_DVS_BASE_URL = "https://veterans.ny.gov"


class NYOfficialSource(StateSource):
    """Fetches from NY DVS Pressroom (static HTML, httpx+BS4).

    The pressroom page lists press releases, publications, and reports
    with h3 > a title links. Pagination via ?page=N (0-indexed).
    """

    def __init__(self, base_url: str = NY_DVS_PRESSROOM_URL, max_pages: int = 3):
        self.base_url = base_url
        self.max_pages = max_pages

    @property
    def source_id(self) -> str:
        return "ny_dvs_news"

    @property
    def state(self) -> str:
        return "NY"

    def fetch(self) -> list[RawSignal]:
        """Fetch press releases from NY DVS pressroom (paginated)."""
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

                signals = self._parse_pressroom(response.text)
                if not signals:
                    break  # No more pages

                for sig in signals:
                    if sig.url not in seen_urls:
                        seen_urls.add(sig.url)
                        all_signals.append(sig)

            except Exception as e:
                logger.error(f"Failed to fetch NY DVS pressroom page {page}: {e}")
                break

        return all_signals

    def _parse_pressroom(self, html: str) -> list[RawSignal]:
        """Parse NY DVS pressroom page HTML.

        NY uses Drupal with WebNY theme. Articles are:
        <article class="webny-teaser teaser--type--webny-{document|whitelisted-content}">
          <a href="/slug">Title</a>
          <a href="/slug">Download/Learn more about Title</a>
        </article>

        The first <a> inside the article has the title text. Type labels
        (Press Releases, Publications, Reports) appear in nested divs.
        """
        soup = BeautifulSoup(html, "html.parser")
        signals = []

        # Primary selector: article.webny-teaser (the Drupal WebNY pattern)
        articles = soup.select("article.webny-teaser")

        if not articles:
            # Fallback: any article element
            articles = soup.select("article")

        if not articles:
            logger.warning("No NY DVS pressroom articles found")
            return []

        logger.debug(f"Found {len(articles)} NY DVS pressroom articles")

        for article in articles:
            try:
                # Skip hero/landing articles (not news items)
                classes = " ".join(article.get("class", []))
                if "hero-landing" in classes:
                    continue

                # First <a> tag with href is the article link
                first_link = article.find("a", href=True)
                if not first_link:
                    continue

                href = first_link.get("href", "")
                if not href or href in ("#", "/", "/pressroom"):
                    continue

                title = first_link.get_text(strip=True)
                # Clean up titles that start with "Download" or "Learn more"
                if title.lower().startswith(("download", "learn more")):
                    continue
                if not title or len(title) < 5:
                    continue

                url = urljoin(NY_DVS_BASE_URL, href)

                # Try to find date from surrounding context
                pub_date = None
                time_elem = article.find("time")
                if time_elem:
                    datetime_attr = time_elem.get("datetime")
                    if datetime_attr and len(datetime_attr) >= 10:
                        pub_date = datetime_attr[:10]
                    else:
                        pub_date = self._parse_date_text(time_elem.get_text())

                if not pub_date:
                    # Try to extract date from any text in the article
                    article_text = article.get_text(" ", strip=True)
                    pub_date = self._extract_date_from_text(article_text)

                # Try to find excerpt from paragraph or description text
                content = None
                for p in article.find_all("p"):
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
                logger.warning(f"Failed to parse NY DVS article: {e}")
                continue

        return signals

    def _extract_date_from_text(self, text: str) -> str | None:
        """Try to find and extract a date from free text."""
        import re

        # Pattern: Month DD, YYYY
        match = re.search(
            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}",
            text,
        )
        if match:
            return self._parse_date_text(match.group(0))

        # Pattern: MM/DD/YYYY
        match = re.search(r"\d{1,2}/\d{1,2}/\d{4}", text)
        if match:
            return self._parse_date_text(match.group(0))

        return None

    def _parse_date_text(self, text: str) -> str | None:
        """Try to parse date from text."""
        # Remove optional comma in "Month DD, YYYY" vs "Month DD YYYY"
        cleaned = text.strip().replace(",", "")
        for fmt in ["%B %d %Y", "%b %d %Y", "%Y-%m-%d", "%m/%d/%Y"]:
            try:
                dt = datetime.strptime(cleaned, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        # Also try with comma
        for fmt in ["%B %d, %Y", "%b %d, %Y"]:
            try:
                dt = datetime.strptime(text.strip(), fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None
