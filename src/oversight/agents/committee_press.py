"""Committee Press Release source agent - HTML scraping version."""

import re
from datetime import UTC, datetime

import requests
from bs4 import BeautifulSoup

from src.resilience.circuit_breaker import oversight_cb
from src.resilience.rate_limiter import external_api_limiter
from src.resilience.wiring import circuit_breaker_sync, with_timeout

from .base import OversightAgent, RawEvent, TimestampResult

# VA-related committee news pages (HTML)
COMMITTEE_SOURCES = {
    "hvac": {
        "url": "https://veterans.house.gov/news/documentquery.aspx?DocumentTypeID=2613",
        "name": "House Veterans' Affairs Committee",
    },
    "svac": {
        "url": "https://www.veterans.senate.gov/",
        "name": "Senate Veterans' Affairs Committee",
    },
}


class CommitteePressAgent(OversightAgent):
    """Agent for fetching VA committee press releases via HTML scraping."""

    source_type = "committee_press"

    def __init__(self, sources: dict = None):
        self.sources = sources or COMMITTEE_SOURCES
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }

    @with_timeout(45, name="committee_press")
    @circuit_breaker_sync(oversight_cb)
    def _fetch_page(self, url: str) -> requests.Response:
        """Fetch a committee page with resilience protection."""
        external_api_limiter.allow()
        resp = requests.get(url, headers=self.headers, timeout=30)
        resp.raise_for_status()
        return resp

    def fetch_new(self, since: datetime | None) -> list[RawEvent]:
        """Fetch new press releases from committee pages."""
        events = []

        for committee, source in self.sources.items():
            try:
                if committee == "hvac":
                    committee_events = self._scrape_hvac(source["url"])
                elif committee == "svac":
                    committee_events = self._scrape_svac(source["url"])
                else:
                    continue

                # Filter by since if provided
                for event in committee_events:
                    if since:
                        ts = self.extract_timestamps(event)
                        if ts.pub_timestamp:
                            try:
                                pub_dt = datetime.fromisoformat(
                                    ts.pub_timestamp.replace("Z", "+00:00")
                                )
                                if pub_dt < since:
                                    continue
                            except ValueError:
                                pass
                    events.append(event)

            except Exception as e:
                print(f"Error scraping {committee}: {e}")
                continue

        return events

    def _scrape_hvac(self, url: str) -> list[RawEvent]:
        """Scrape House Veterans' Affairs Committee news page."""
        events = []

        try:
            resp = self._fetch_page(url)
        except Exception as e:
            print(f"Error fetching HVAC page: {e}")
            return events

        soup = BeautifulSoup(resp.text, "html.parser")

        # Find news items - they're in article.newsblocker elements
        for item in soup.select("article.newsblocker"):
            try:
                # Find the title link
                title_link = item.select_one("h2.newsie-titler a")
                if not title_link:
                    continue

                title = title_link.get_text(strip=True)
                link = title_link.get("href", "")

                # Build full URL
                if not link.startswith("http"):
                    if link.startswith("/"):
                        link = f"https://veterans.house.gov{link}"
                    else:
                        link = f"https://veterans.house.gov/news/{link}"

                # Find date from time element with datetime attribute
                date_elem = item.select_one("time[datetime]")
                date_str = None
                if date_elem:
                    # Prefer datetime attribute (YYYY-MM-DD format)
                    date_str = date_elem.get("datetime") or date_elem.get_text(strip=True)

                # Find summary/excerpt
                summary_elem = item.select_one("div.newsbody p")
                summary = summary_elem.get_text(strip=True)[:500] if summary_elem else ""

                events.append(
                    RawEvent(
                        url=link,
                        title=title,
                        raw_html=str(item),
                        fetched_at=datetime.now(UTC).isoformat(),
                        excerpt=summary,
                        metadata={
                            "published": date_str,
                            "committee": "hvac",
                        },
                    )
                )
            except Exception:
                continue

        return events

    def _scrape_svac(self, url: str) -> list[RawEvent]:
        """Scrape Senate Veterans' Affairs Committee homepage for news."""
        events = []

        try:
            resp = self._fetch_page(url)
        except Exception as e:
            print(f"Error fetching SVAC page: {e}")
            return events

        soup = BeautifulSoup(resp.text, "html.parser")

        # Senate page has news in different sections - look for news links
        # Based on the browser snapshot, there are links like "Chairman Moran..." etc.
        seen_urls = set()

        for link in soup.select("a[href]"):
            href = link.get("href", "")
            title = link.get_text(strip=True)

            # Filter to likely press release links
            if not href or not title:
                continue
            if len(title) < 30:
                continue
            # Skip navigation/menu links
            if href in ["#", "/", "/hearings", "/newsroom"]:
                continue
            if "Read more" in title:
                continue

            # Check if it looks like a news item (contains news-related keywords or is a press release path)
            is_news = any(kw in href.lower() for kw in ["/press/", "/newsroom/", "/news/"]) or any(
                kw in title.lower()
                for kw in ["introduces", "statement", "applauds", "urges", "leads", "announces"]
            )

            if not is_news:
                continue

            if not href.startswith("http"):
                href = f"https://www.veterans.senate.gov{href}"

            if href in seen_urls:
                continue
            seen_urls.add(href)

            events.append(
                RawEvent(
                    url=href,
                    title=title,
                    raw_html="",
                    fetched_at=datetime.now(UTC).isoformat(),
                    excerpt="",
                    metadata={
                        "published": None,
                        "committee": "svac",
                    },
                )
            )

        return events

    def backfill(self, start: datetime, end: datetime) -> list[RawEvent]:
        """Backfill - HTML pages only have recent items."""
        all_events = self.fetch_new(since=None)
        return [e for e in all_events if self._in_range(e, start, end)]

    def _in_range(self, event: RawEvent, start: datetime, end: datetime) -> bool:
        ts = self.extract_timestamps(event)
        if ts.pub_timestamp:
            try:
                pub_dt = datetime.fromisoformat(ts.pub_timestamp.replace("Z", "+00:00"))
                return start <= pub_dt <= end
            except ValueError:
                pass
        return True  # Include if we can't determine date

    def extract_timestamps(self, raw: RawEvent) -> TimestampResult:
        """Extract timestamps from press release."""
        pub_timestamp = None
        pub_precision = "unknown"
        pub_source = "missing"

        published = raw.metadata.get("published")
        if published:
            published = published.strip()
            # Try common date formats
            formats = [
                "%Y-%m-%d",  # 2026-01-29 (from datetime attr)
                "%B %d, %Y",  # January 29, 2026
                "%b %d, %Y",  # Jan 29, 2026
                "%m/%d/%Y",  # 01/29/2026
            ]
            for fmt in formats:
                try:
                    dt = datetime.strptime(published, fmt)
                    dt = dt.replace(tzinfo=UTC)
                    pub_timestamp = dt.isoformat()
                    pub_precision = "date"
                    pub_source = "extracted"
                    break
                except ValueError:
                    continue

        # Fallback: try to extract date from URL
        # Senate URLs have format: /2026/1/title-slug
        if not pub_timestamp:
            url = raw.url
            url_date_match = re.search(r"/(\d{4})/(\d{1,2})/", url)
            if url_date_match:
                year = int(url_date_match.group(1))
                month = int(url_date_match.group(2))
                if 2000 <= year <= 2100 and 1 <= month <= 12:
                    # Use first day of month as approximation
                    dt = datetime(year, month, 1, tzinfo=UTC)
                    pub_timestamp = dt.isoformat()
                    pub_precision = "month"
                    pub_source = "inferred_from_url"

        return TimestampResult(
            pub_timestamp=pub_timestamp,
            pub_precision=pub_precision,
            pub_source=pub_source,
        )

    def extract_canonical_refs(self, raw: RawEvent) -> dict:
        """Extract press release reference."""
        refs = {}

        committee = raw.metadata.get("committee")
        if committee:
            refs["committee"] = committee

        return refs
