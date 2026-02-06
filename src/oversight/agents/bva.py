"""Board of Veterans' Appeals (BVA) decision source agent.

Fetches BVA decisions via the search.usa.gov BVA decisions index
and parses individual decision text files from va.gov/vetapp/.
"""

import re
from datetime import datetime, timezone
from typing import Optional

import requests
from bs4 import BeautifulSoup

from .base import OversightAgent, RawEvent, TimestampResult


# search.usa.gov BVA decisions affiliate
BVA_SEARCH_URL = "https://search.usa.gov/search"
BVA_AFFILIATE = "bvadecisions"

# Pattern for BVA citation numbers: legacy (YYMMNNNNN) and AMA (AYYMMNNNN)
BVA_CITATION_PATTERN = re.compile(r"([A-Z]?\d{8,9})")

# Pattern for extracting decision date from text file header
BVA_DATE_PATTERN = re.compile(
    r"Decision\s+Date:\s*(\d{2}/\d{2}/\d{2})", re.IGNORECASE
)

# Pattern for docket number
BVA_DOCKET_PATTERN = re.compile(
    r"DOCKET\s+NO\.\s*([\d\-]+)", re.IGNORECASE
)

# Pattern for full date in body (e.g., "September 30, 2025")
BVA_FULL_DATE_PATTERN = re.compile(
    r"DATE:\s+(\w+ \d{1,2},\s*\d{4})", re.IGNORECASE
)

# Outcome keywords for classification
BVA_OUTCOMES = {
    "granted": "granted",
    "denied": "denied",
    "remanded": "remanded",
    "dismissed": "dismissed",
}


class BVAAgent(OversightAgent):
    """Agent for fetching Board of Veterans' Appeals decisions."""

    source_type = "bva"

    def __init__(
        self,
        search_url: str = BVA_SEARCH_URL,
        affiliate: str = BVA_AFFILIATE,
    ):
        self.search_url = search_url
        self.affiliate = affiliate
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36"
        }

    def fetch_new(self, since: Optional[datetime]) -> list[RawEvent]:
        """
        Fetch recent BVA decisions via search.usa.gov.

        Searches for recent decisions and filters by date if since is provided.
        """
        events = []
        seen_urls = set()

        # Search for recent decisions across multiple queries
        queries = ["service connection", "disability rating", "PTSD", "remand"]

        for query in queries:
            try:
                page_events = self._search_decisions(query, since)
                for event in page_events:
                    if event.url not in seen_urls:
                        seen_urls.add(event.url)
                        events.append(event)
            except Exception as e:
                # Log but continue with other queries
                print(f"BVA search query '{query}' failed: {e}")

        return events

    def _search_decisions(
        self,
        query: str,
        since: Optional[datetime],
    ) -> list[RawEvent]:
        """Search for BVA decisions via search.usa.gov."""
        events = []

        try:
            resp = requests.get(
                self.search_url,
                params={
                    "affiliate": self.affiliate,
                    "query": query,
                },
                headers=self.headers,
                timeout=30,
            )
            resp.raise_for_status()
        except Exception as e:
            raise ValueError(f"BVA search failed: {e}")

        soup = BeautifulSoup(resp.text, "html.parser")
        results = soup.select(".content-block-item.result")

        for result in results:
            link = result.find("a")
            if not link:
                continue

            href = link.get("href", "")
            if not href.endswith(".txt"):
                continue

            # Extract citation from filename
            filename = href.rsplit("/", 1)[-1].replace(".txt", "")
            citation_match = BVA_CITATION_PATTERN.match(filename)
            citation = citation_match.group(1) if citation_match else filename

            # Extract year from URL path (vetappYY)
            year_match = re.search(r"vetapp(\d{2})", href)
            year = f"20{year_match.group(1)}" if year_match else None

            # Get snippet text from the result
            snippet_text = result.get_text(strip=True)
            # Remove the filename/URL prefix from snippet
            if href in snippet_text:
                snippet_text = snippet_text.split(href, 1)[-1]
            snippet_text = snippet_text[:500].strip(".")

            # Build metadata
            metadata = {
                "citation_nr": citation,
                "year": year,
                "source_url": href,
            }

            # If we have a year and since filter, do a rough year check
            if since and year:
                try:
                    if int(year) < since.year:
                        continue
                except ValueError:
                    pass

            fetched_at = datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )

            events.append(
                RawEvent(
                    url=href,
                    title=f"BVA Decision {citation}",
                    raw_html=snippet_text,
                    fetched_at=fetched_at,
                    excerpt=snippet_text[:300] if snippet_text else None,
                    metadata=metadata,
                )
            )

        return events

    def backfill(self, start: datetime, end: datetime) -> list[RawEvent]:
        """
        Backfill historical BVA decisions.

        Uses search.usa.gov to find decisions and filters by extracted date.
        """
        all_events = self.fetch_new(since=start)

        filtered = []
        for event in all_events:
            ts = self.extract_timestamps(event)
            if ts.pub_timestamp:
                try:
                    pub_dt = datetime.fromisoformat(
                        ts.pub_timestamp.replace("Z", "+00:00")
                    )
                    if start <= pub_dt <= end:
                        filtered.append(event)
                except (ValueError, TypeError):
                    # Include if we can't determine date
                    filtered.append(event)
            else:
                # Include if we can't determine date
                filtered.append(event)

        return filtered

    def fetch_decision_detail(self, url: str) -> Optional[dict]:
        """
        Fetch and parse a BVA decision text file for detailed metadata.

        Returns dict with: citation_nr, decision_date, docket_no,
        decision_type, issues, full_text
        """
        try:
            resp = requests.get(url, headers=self.headers, timeout=30)
            resp.raise_for_status()
        except Exception:
            return None

        text = resp.text
        detail = {}

        # Extract citation number
        cit_match = re.search(
            r"Citation\s+Nr:\s*([A-Z]?\d+)", text, re.IGNORECASE
        )
        if cit_match:
            detail["citation_nr"] = cit_match.group(1)

        # Extract decision date (short format: MM/DD/YY)
        date_match = BVA_DATE_PATTERN.search(text)
        if date_match:
            detail["decision_date_raw"] = date_match.group(1)

        # Extract full date (e.g., "September 30, 2025")
        full_date_match = BVA_FULL_DATE_PATTERN.search(text)
        if full_date_match:
            detail["decision_date_full"] = full_date_match.group(1)

        # Extract docket number
        docket_match = BVA_DOCKET_PATTERN.search(text)
        if docket_match:
            detail["docket_no"] = docket_match.group(1)

        # Determine outcome type from ORDER section
        order_section = text.split("ORDER", 1)
        if len(order_section) > 1:
            order_text = order_section[1][:2000].lower()
            outcomes = set()
            for keyword, label in BVA_OUTCOMES.items():
                if keyword in order_text:
                    outcomes.add(label)
            if outcomes:
                detail["decision_types"] = sorted(outcomes)

        # Store truncated full text
        detail["full_text"] = text[:5000]

        return detail

    def extract_timestamps(self, raw: RawEvent) -> TimestampResult:
        """Extract timestamps from BVA decision metadata."""
        pub_timestamp = None
        pub_precision = "unknown"
        pub_source = "missing"

        # Try decision_date_full from metadata (e.g., "September 30, 2025")
        full_date = raw.metadata.get("decision_date_full")
        if full_date:
            pub_dt = self._parse_date(full_date)
            if pub_dt:
                pub_timestamp = pub_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                pub_precision = "date"
                pub_source = "extracted"

        # Try decision_date_raw (MM/DD/YY)
        if not pub_timestamp:
            raw_date = raw.metadata.get("decision_date_raw")
            if raw_date:
                pub_dt = self._parse_date(raw_date)
                if pub_dt:
                    pub_timestamp = pub_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                    pub_precision = "date"
                    pub_source = "extracted"

        # Fallback: infer year from URL (vetappYY)
        if not pub_timestamp:
            year = raw.metadata.get("year")
            if year:
                try:
                    pub_dt = datetime(int(year), 1, 1, tzinfo=timezone.utc)
                    pub_timestamp = pub_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                    pub_precision = "month"
                    pub_source = "inferred"
                except (ValueError, TypeError):
                    pass

        return TimestampResult(
            pub_timestamp=pub_timestamp,
            pub_precision=pub_precision,
            pub_source=pub_source,
        )

    def extract_canonical_refs(self, raw: RawEvent) -> dict:
        """Extract BVA citation and docket for deduplication."""
        refs = {}

        citation = raw.metadata.get("citation_nr")
        if citation:
            refs["bva_citation"] = citation

        docket = raw.metadata.get("docket_no")
        if docket:
            refs["bva_docket"] = docket

        # Decision type if available
        decision_types = raw.metadata.get("decision_types")
        if decision_types:
            refs["decision_types"] = decision_types

        return refs

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse various BVA date formats to datetime."""
        if not date_str:
            return None

        formats = [
            "%m/%d/%y",  # 09/30/25
            "%m/%d/%Y",  # 09/30/2025
            "%Y-%m-%d",  # 2025-09-30
            "%B %d, %Y",  # September 30, 2025
            "%b %d, %Y",  # Sep 30, 2025
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue

        return None
