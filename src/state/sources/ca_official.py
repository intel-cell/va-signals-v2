"""California official sources - CalVet Newsroom."""

import logging
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.state.common import RawSignal
from src.state.sources.base import StateSource

logger = logging.getLogger(__name__)

# CalVet site (www.calvet.ca.gov) is currently unreachable - connection reset
# CA coverage comes from RSS feeds (CalMatters, LA Times, Google News)
CALVET_NEWS_URL = "https://www.calvet.ca.gov/VetServices/Pages/News.aspx"
CALVET_DISABLED = True  # Site unreachable - enable when accessible


class CAOfficialSource(StateSource):
    """Fetches from CalVet Newsroom using Playwright for JS rendering."""

    def __init__(self, base_url: str = CALVET_NEWS_URL):
        self.base_url = base_url

    @property
    def source_id(self) -> str:
        return "ca_calvet_news"

    @property
    def state(self) -> str:
        return "CA"

    def fetch(self) -> list[RawSignal]:
        """Fetch news from CalVet website using Playwright."""
        if CALVET_DISABLED:
            logger.info("CalVet source disabled (site unreachable)")
            return []

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error(
                "Playwright not installed - run: pip install playwright && playwright install chromium"
            )
            return []

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(self.base_url, wait_until="networkidle", timeout=30000)

                # Wait for content to load
                page.wait_for_timeout(2000)

                html = page.content()
                browser.close()

            return self._parse_calvet_news(html)
        except Exception as e:
            logger.error(f"Failed to fetch CalVet news: {e}")
            return []

    def _parse_calvet_news(self, html: str) -> list[RawSignal]:
        """Parse CalVet news page HTML."""
        soup = BeautifulSoup(html, "html.parser")
        signals = []

        # CalVet uses SharePoint - try multiple selectors
        selectors = [
            ".news-article",
            "article",
            ".post",
            ".ms-listviewtable tr",  # SharePoint list
            "[data-automationid='ListCell']",  # Modern SharePoint
            ".dfwp-item",  # SharePoint web part
        ]

        articles = []
        for selector in selectors:
            articles = soup.select(selector)
            if articles:
                logger.debug(f"Found {len(articles)} articles with selector: {selector}")
                break

        for article in articles:
            try:
                # Try multiple title selectors
                title_elem = (
                    article.select_one("h3 a, h2 a, .title a")
                    or article.select_one("a[href*='News']")
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

                url = urljoin("https://www.calvet.ca.gov/", href)

                # Try to find date
                date_elem = article.select_one(".date, time, .pub-date, .ms-vb2")
                pub_date = None
                if date_elem:
                    datetime_attr = date_elem.get("datetime")
                    if datetime_attr and len(datetime_attr) >= 10:
                        pub_date = datetime_attr[:10]
                    else:
                        pub_date = self._parse_date_text(date_elem.get_text())

                # Try to find excerpt
                excerpt_elem = article.select_one("p, .excerpt, .summary, .ms-vb2")
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

    def _parse_date_text(self, text: str) -> str | None:
        """Try to parse date from text like '01/19/2026'."""
        for fmt in ["%m/%d/%Y", "%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"]:
            try:
                dt = datetime.strptime(text.strip(), fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None
