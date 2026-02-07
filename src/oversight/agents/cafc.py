"""Court of Appeals for the Federal Circuit (CAFC) source agent."""

import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import feedparser
import requests
from bs4 import BeautifulSoup

from src.resilience.circuit_breaker import oversight_cb
from src.resilience.rate_limiter import external_api_limiter
from src.resilience.wiring import circuit_breaker_sync, with_timeout

from .base import OversightAgent, RawEvent, TimestampResult

# RSS feed for opinions and orders
CAFC_RSS_URL = "https://www.cafc.uscourts.gov/category/opinion-order/feed/"

# Opinions page for HTML scraping fallback
CAFC_OPINIONS_URL = "https://www.cafc.uscourts.gov/home/case-information/opinions-orders/"

# Case number pattern: YY-NNNN or YYYY-NNNN
CAFC_CASE_PATTERN = re.compile(r"(\d{2,4})-(\d{3,5})")

# Date pattern for extracting from URLs/filenames: M-D-YYYY or MM-DD-YYYY
CAFC_DATE_PATTERN = re.compile(r"(\d{1,2})-(\d{1,2})-(\d{4})")


class CAFCAgent(OversightAgent):
    """Agent for fetching CAFC veterans case decisions."""

    source_type = "cafc"

    def __init__(self, rss_url: str = CAFC_RSS_URL, opinions_url: str = CAFC_OPINIONS_URL):
        self.rss_url = rss_url
        self.opinions_url = opinions_url
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }
        # VA party names to filter for
        self.va_parties = [
            "McDonough",  # Current VA Secretary
            "Collins",  # Current VA Secretary (Denis McDonough, but cases often show as "Collins")
            "Wilkie",
            "Shulkin",
            "Secretary of Veterans Affairs",
            "Department of Veterans Affairs",
            "Veterans Affairs",
        ]
        # CAVC = Court of Appeals for Veterans Claims - always VA related
        self.va_origins = ["CAVC"]

    @with_timeout(45, name="cafc_rss")
    @circuit_breaker_sync(oversight_cb)
    def _fetch_feed(self, url: str):
        """Fetch and parse an RSS feed with resilience protection."""
        return feedparser.parse(url)

    @with_timeout(45, name="cafc_html")
    @circuit_breaker_sync(oversight_cb)
    def _fetch_page(self, url: str) -> requests.Response:
        """Fetch an HTML page with resilience protection."""
        resp = requests.get(url, headers=self.headers, timeout=30)
        resp.raise_for_status()
        return resp

    def fetch_new(self, since: datetime | None) -> list[RawEvent]:
        """
        Fetch new CAFC decisions related to VA.

        Tries RSS feed first, falls back to HTML scraping.
        Filters for VA-related cases by origin (CAVC) or party names.
        """
        events = []

        # Try RSS feed first
        try:
            rss_events = self._fetch_from_rss(since)
            events.extend(rss_events)
        except Exception as e:
            print(f"CAFC RSS fetch failed: {e}, trying HTML scraping")

        # If RSS returned nothing, try HTML scraping
        if not events:
            try:
                html_events = self._fetch_from_html(since)
                events.extend(html_events)
            except Exception as e:
                print(f"CAFC HTML scraping failed: {e}")

        return events

    def _fetch_from_rss(self, since: datetime | None) -> list[RawEvent]:
        """Fetch opinions from RSS feed."""
        external_api_limiter.allow()
        feed = self._fetch_feed(self.rss_url)
        events = []

        if feed.bozo and not feed.entries:
            raise ValueError(f"RSS feed error: {feed.bozo_exception}")

        for entry in feed.entries:
            # Parse publication date
            pub_date = None
            if hasattr(entry, "published"):
                try:
                    pub_date = parsedate_to_datetime(entry.published)
                except (ValueError, TypeError):
                    pass

            # Skip if older than since
            if since and pub_date and pub_date < since:
                continue

            title = getattr(entry, "title", "")
            link = getattr(entry, "link", "")
            summary = getattr(entry, "summary", "")

            # Check if VA-related
            if not self._is_va_related(title, summary, link):
                continue

            # Extract metadata
            metadata = {
                "published": getattr(entry, "published", None),
            }

            # Try to extract case number from title/link
            case_match = CAFC_CASE_PATTERN.search(f"{link} {title}")
            if case_match:
                metadata["case_number"] = f"{case_match.group(1)}-{case_match.group(2)}"

            # Check if precedential
            metadata["precedential"] = "precedential" in title.lower()

            fetched_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

            events.append(
                RawEvent(
                    url=link,
                    title=title,
                    raw_html=summary,
                    fetched_at=fetched_at,
                    excerpt=summary[:500] if summary else None,
                    metadata=metadata,
                )
            )

        return events

    def _fetch_from_html(self, since: datetime | None) -> list[RawEvent]:
        """Scrape opinions from HTML page."""
        events = []

        try:
            external_api_limiter.allow()
            resp = self._fetch_page(self.opinions_url)
        except Exception as e:
            raise ValueError(f"Failed to fetch opinions page: {e}") from e

        soup = BeautifulSoup(resp.text, "html.parser")

        # The opinions are in a table - find all table rows
        # Looking for rows with: Release Date, Appeal Number, Origin, Document Type, Case Name, Status
        table = soup.find("table")
        if not table:
            # Try finding data in other formats (the page uses JavaScript rendering)
            # Look for links that match the opinion URL pattern
            return self._scrape_opinion_links(soup, since)

        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) < 5:
                continue

            try:
                release_date = cells[0].get_text(strip=True)
                appeal_number = cells[1].get_text(strip=True)
                origin = cells[2].get_text(strip=True)
                doc_type = cells[3].get_text(strip=True)

                # Get case name and link
                case_cell = cells[4]
                link_elem = case_cell.find("a")
                if link_elem:
                    case_name = link_elem.get_text(strip=True)
                    href = link_elem.get("href", "")
                else:
                    case_name = case_cell.get_text(strip=True)
                    href = ""

                status = cells[5].get_text(strip=True) if len(cells) > 5 else ""

                # Build full URL
                if href and not href.startswith("http"):
                    href = f"https://www.cafc.uscourts.gov{href}"

                # Check if VA-related (CAVC origin or party names)
                if origin not in self.va_origins and not self._is_va_related(case_name, "", href):
                    continue

                # Parse date
                pub_dt = self._parse_date(release_date)
                if since and pub_dt and pub_dt < since:
                    continue

                metadata = {
                    "published": release_date,
                    "case_number": appeal_number,
                    "origin": origin,
                    "doc_type": doc_type,
                    "precedential": status.lower() == "precedential",
                }

                fetched_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

                events.append(
                    RawEvent(
                        url=href,
                        title=f"{case_name} ({appeal_number})",
                        raw_html="",
                        fetched_at=fetched_at,
                        excerpt=f"{doc_type} - {status}",
                        metadata=metadata,
                    )
                )

            except Exception:
                continue

        return events

    def _scrape_opinion_links(self, soup: BeautifulSoup, since: datetime | None) -> list[RawEvent]:
        """Fallback: scrape opinion links from page."""
        events = []
        seen_urls = set()

        # Look for PDF links that match opinion pattern
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            title = link.get_text(strip=True)

            # Filter for opinion/order PDFs
            if not href or "opinions-orders/" not in href.lower():
                continue
            if not href.endswith(".pdf"):
                continue

            # Build full URL
            if not href.startswith("http"):
                href = f"https://www.cafc.uscourts.gov{href}"

            if href in seen_urls:
                continue
            seen_urls.add(href)

            # Check if VA-related
            if not self._is_va_related(title, "", href):
                continue

            # Try to extract date from filename
            # Pattern: XX-XXXX.TYPE.M-D-YYYY_XXXXX.pdf
            date_match = CAFC_DATE_PATTERN.search(href)
            pub_date = None
            pub_str = None
            if date_match:
                try:
                    month, day, year = (
                        int(date_match.group(1)),
                        int(date_match.group(2)),
                        int(date_match.group(3)),
                    )
                    pub_date = datetime(year, month, day, tzinfo=UTC)
                    pub_str = pub_date.strftime("%m/%d/%Y")
                except ValueError:
                    pass

            if since and pub_date and pub_date < since:
                continue

            # Extract case number
            case_match = CAFC_CASE_PATTERN.search(href)
            case_number = f"{case_match.group(1)}-{case_match.group(2)}" if case_match else None

            metadata = {
                "published": pub_str,
                "case_number": case_number,
            }

            fetched_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

            events.append(
                RawEvent(
                    url=href,
                    title=title or f"CAFC {case_number}" if case_number else "CAFC Opinion",
                    raw_html="",
                    fetched_at=fetched_at,
                    excerpt=None,
                    metadata=metadata,
                )
            )

        return events

    def _is_va_related(self, title: str, summary: str, url: str) -> bool:
        """Check if a case is VA-related based on party names or content."""
        combined = f"{title} {summary} {url}".upper()

        # Check for CAVC in URL (Court of Appeals for Veterans Claims)
        if "CAVC" in combined:
            return True

        # Check for VA party names
        for party in self.va_parties:
            if party.upper() in combined:
                return True

        return False

    def _parse_date(self, date_str: str) -> datetime | None:
        """Parse date string to datetime."""
        if not date_str:
            return None

        formats = [
            "%m/%d/%Y",  # 01/05/2026
            "%Y-%m-%d",  # 2026-01-05
            "%B %d, %Y",  # January 5, 2026
            "%b %d, %Y",  # Jan 5, 2026
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                return dt.replace(tzinfo=UTC)
            except ValueError:
                continue

        return None

    def backfill(self, start: datetime, end: datetime) -> list[RawEvent]:
        """
        Backfill historical CAFC decisions.

        Note: RSS/HTML only have recent items. For full backfill,
        would need PACER access or archived pages.
        """
        # Fetch all available and filter by date range
        all_events = self.fetch_new(since=None)

        filtered = []
        for event in all_events:
            ts = self.extract_timestamps(event)
            if ts.pub_timestamp:
                try:
                    pub_dt = datetime.fromisoformat(ts.pub_timestamp.replace("Z", "+00:00"))
                    if start <= pub_dt <= end:
                        filtered.append(event)
                except (ValueError, TypeError):
                    pass
            else:
                # Include if we can't determine date
                filtered.append(event)

        return filtered

    def extract_timestamps(self, raw: RawEvent) -> TimestampResult:
        """Extract timestamps from CAFC decision."""
        pub_timestamp = None
        pub_precision = "unknown"
        pub_source = "missing"

        # Try to parse from metadata
        published = raw.metadata.get("published")
        if published:
            pub_dt = self._parse_date(published)
            if pub_dt:
                pub_timestamp = pub_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                pub_precision = "date"
                pub_source = "extracted"

        # Fallback: try to extract from URL
        if not pub_timestamp:
            date_match = CAFC_DATE_PATTERN.search(raw.url)
            if date_match:
                try:
                    month, day, year = (
                        int(date_match.group(1)),
                        int(date_match.group(2)),
                        int(date_match.group(3)),
                    )
                    pub_dt = datetime(year, month, day, tzinfo=UTC)
                    pub_timestamp = pub_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                    pub_precision = "date"
                    pub_source = "inferred_from_url"
                except ValueError:
                    pass

        return TimestampResult(
            pub_timestamp=pub_timestamp,
            pub_precision=pub_precision,
            pub_source=pub_source,
        )

    def extract_canonical_refs(self, raw: RawEvent) -> dict:
        """Extract CAFC case number."""
        refs = {}

        # Try metadata first
        case_number = raw.metadata.get("case_number")
        if case_number:
            refs["cafc_case"] = case_number
        else:
            # Extract from URL/title
            combined = f"{raw.url} {raw.title}"
            match = CAFC_CASE_PATTERN.search(combined)
            if match:
                refs["cafc_case"] = f"{match.group(1)}-{match.group(2)}"

        # Origin if available
        origin = raw.metadata.get("origin")
        if origin:
            refs["origin"] = origin

        # Check if precedential
        if raw.metadata.get("precedential") or "precedential" in raw.title.lower():
            refs["is_precedential"] = True

        return refs
