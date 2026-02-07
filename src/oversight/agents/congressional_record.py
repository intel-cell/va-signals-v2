"""Congressional Record source agent."""

import logging
import re
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import requests

from src.resilience.circuit_breaker import congress_api_cb
from src.resilience.rate_limiter import external_api_limiter
from src.resilience.wiring import circuit_breaker_sync, with_timeout

from ...secrets import get_env_or_keychain
from .base import OversightAgent, RawEvent, TimestampResult

logger = logging.getLogger(__name__)

BASE_API_URL = "https://api.congress.gov/v3"


class CongressionalRecordAgent(OversightAgent):
    """Agent for fetching VA-related Congressional Record entries."""

    source_type = "congressional_record"

    def __init__(self):
        # Use word boundaries for VA to avoid "EVA" matching
        self.search_terms = ["veterans", r"\bVA\b", "Department of Veterans"]
        self.api_key = get_env_or_keychain("CONGRESS_API_KEY", "congress-api")

    @with_timeout(30, name="congress_html")
    @circuit_breaker_sync(congress_api_cb)
    def _fetch_html(self, url: str) -> str | None:
        """Fetch raw HTML from a URL with resilience protection."""
        external_api_limiter.allow()
        try:
            resp = requests.get(url, headers={"User-Agent": "VA-Signals/1.0"}, timeout=25)
            if resp.status_code == 200:
                return resp.text
            logger.warning("Non-200 status %d fetching HTML from %s", resp.status_code, url)
            return None
        except requests.RequestException as e:
            logger.error("Error fetching HTML from %s: %s", url, e)
            return None

    @with_timeout(45, name="congress_api")
    @circuit_breaker_sync(congress_api_cb)
    def _fetch_json(self, url: str) -> dict[str, Any]:
        """Helper to fetch JSON from API."""
        if not self.api_key:
            raise RuntimeError("CONGRESS_API_KEY not found")

        sep = "&" if "?" in url else "?"
        full_url = f"{url}{sep}api_key={self.api_key}&format=json"

        external_api_limiter.allow()
        resp = requests.get(full_url, headers={"User-Agent": "VA-Signals/1.0"})
        resp.raise_for_status()
        return resp.json()

    def fetch_new(self, since: datetime | None) -> list[RawEvent]:
        """
        Fetch new Congressional Record entries.
        """
        if not since:
            # Default to last 3 days if no state
            since = datetime.now(UTC) - timedelta(days=3)

        events = []
        current_date = datetime.now(UTC)

        # Iterate days from since to now
        # Note: API uses y/m/d params
        delta = current_date - since
        for i in range(delta.days + 1):
            day = since + timedelta(days=i)

            # Skip future dates
            if day > current_date:
                break

            try:
                day_events = self._fetch_for_date(day)
                events.extend(day_events)
                # Be nice to the API
                time.sleep(0.5)
            except Exception as e:
                # Log error but continue
                logger.error("Error fetching CR for %s: %s", day.date(), e)

        return events

    def _fetch_for_date(self, date: datetime) -> list[RawEvent]:
        """Fetch CR entries for a specific date."""
        y, m, d = date.strftime("%Y"), date.strftime("%m"), date.strftime("%d")
        url = f"{BASE_API_URL}/daily-congressional-record?y={y}&m={m}&d={d}"

        try:
            data = self._fetch_json(url)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return []  # No record for this day
            raise

        issues = data.get("dailyCongressionalRecord", [])
        events = []

        for issue in issues:
            issue_url = issue.get("url")
            if not issue_url:
                continue

            # Strip existing format param if present to avoid duplication
            if "?format=json" in issue_url:
                issue_url = issue_url.replace("?format=json", "")

            try:
                issue_detail = self._fetch_json(issue_url)

                # Get articles URL
                articles_url = (
                    issue_detail.get("issue", {})
                    .get("fullIssue", {})
                    .get("articles", {})
                    .get("url")
                )
                if not articles_url:
                    continue

                if "?format=json" in articles_url:
                    articles_url = articles_url.replace("?format=json", "")

                articles_data = self._fetch_json(articles_url)

                # Process articles
                sections = articles_data.get("articles", [])
                for section in sections:
                    section_name = section.get("name", "Unknown")

                    # Skip Daily Digest if we want primary source only, but it's often good summary
                    # Let's keep it for now but maybe downrank it later

                    for article in section.get("sectionArticles", []):
                        if self._is_relevant(article):
                            event = self._create_event(article, issue, section_name)
                            if event:
                                events.append(event)

            except Exception as e:
                logger.error("Error processing issue %s: %s", issue_url, e)
                continue

        return events

    def _is_relevant(self, article: dict) -> bool:
        """Check if article is relevant based on title."""
        title = article.get("title", "")
        if not title:
            return False

        for term in self.search_terms:
            if term.startswith(r"\b"):
                # Regex match
                if re.search(term, title, re.IGNORECASE):
                    return True
            else:
                # Substring match
                if term.lower() in title.lower():
                    return True
        return False

    def _create_event(self, article: dict, issue_meta: dict, section_name: dict) -> RawEvent | None:
        """Convert API article to RawEvent."""
        title = article.get("title")
        if not title:
            return None

        # Find HTML text URL
        text_url = None
        pdf_url = None
        for t in article.get("text", []):
            if t.get("type") == "Formatted Text":
                text_url = t.get("url")
            elif t.get("type") == "PDF":
                pdf_url = t.get("url")

        url = text_url or pdf_url
        if not url:
            return None

        # Construct ID
        # Use startPage if available, otherwise hash title
        start_page = article.get("startPage", "unknown")
        vol = issue_meta.get("volumeNumber")
        iss = issue_meta.get("issueNumber")

        date_str = issue_meta.get("issueDate")

        # Fetch raw HTML if we have a text URL
        raw_html = ""
        if text_url:
            html = self._fetch_html(text_url)
            if html:
                raw_html = html

        return RawEvent(
            title=title,
            raw_html=raw_html,
            excerpt=f"Congressional Record ({section_name}) - Pages {start_page}-{article.get('endPage')}",
            url=url,
            fetched_at=datetime.now(UTC).isoformat(),
            metadata={
                "date": date_str,
                "chamber": section_name,
                "volume": vol,
                "issue": iss,
                "pages": f"{start_page}-{article.get('endPage')}",
                "pdf_url": pdf_url,
                "source_id": f"cr-{vol}-{iss}-{start_page}",  # Store ID in metadata
            },
        )

    def backfill(self, start: datetime, end: datetime) -> list[RawEvent]:
        """Backfill historical entries."""
        # Reuse fetch_new logic but iterate range
        return self.fetch_new(start)

    def extract_timestamps(self, raw: RawEvent) -> TimestampResult:
        """Extract timestamps from Congressional Record entry."""
        pub_timestamp = None
        date_str = raw.metadata.get("date")
        if date_str:
            try:
                # API returns ISO format like "2026-01-29T05:00:00Z"
                pub_timestamp = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except ValueError:
                pass

        pub_precision = "date" if pub_timestamp else "unknown"
        pub_source = "api" if pub_timestamp else "missing"

        return TimestampResult(
            pub_timestamp=pub_timestamp,
            pub_precision=pub_precision,
            pub_source=pub_source,
        )

    def extract_canonical_refs(self, raw: RawEvent) -> dict:
        """Extract Congressional Record reference."""
        refs = {}

        # Extract from metadata if available
        vol = raw.metadata.get("volume")
        page = raw.metadata.get("pages", "").split("-")[0]

        if vol and page and page != "unknown":
            # Standard CR citation: 172 Cong. Rec. S357
            refs["citation"] = f"{vol} Cong. Rec. {page}"

        return refs
