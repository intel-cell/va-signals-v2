"""Congressional Record source agent."""

import re
import time
import requests
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

from .base import OversightAgent, RawEvent, TimestampResult
from ...secrets import get_env_or_keychain

BASE_API_URL = "https://api.congress.gov/v3"

class CongressionalRecordAgent(OversightAgent):
    """Agent for fetching VA-related Congressional Record entries."""

    source_type = "congressional_record"

    def __init__(self):
        # Use word boundaries for VA to avoid "EVA" matching
        self.search_terms = ["veterans", r"\bVA\b", "Department of Veterans"]
        self.api_key = get_env_or_keychain("CONGRESS_API_KEY", "congress-api")

    def _fetch_json(self, url: str) -> Dict[str, Any]:
        """Helper to fetch JSON from API."""
        if not self.api_key:
            raise RuntimeError("CONGRESS_API_KEY not found")
            
        sep = "&" if "?" in url else "?"
        full_url = f"{url}{sep}api_key={self.api_key}&format=json"
        
        resp = requests.get(full_url, headers={"User-Agent": "VA-Signals/1.0"})
        resp.raise_for_status()
        return resp.json()

    def fetch_new(self, since: Optional[datetime]) -> list[RawEvent]:
        """
        Fetch new Congressional Record entries.
        """
        if not since:
            # Default to last 3 days if no state
            since = datetime.now(timezone.utc) - timedelta(days=3)

        events = []
        current_date = datetime.now(timezone.utc)
        
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
                print(f"Error fetching CR for {day.date()}: {e}")
                
        return events

    def _fetch_for_date(self, date: datetime) -> List[RawEvent]:
        """Fetch CR entries for a specific date."""
        y, m, d = date.strftime("%Y"), date.strftime("%m"), date.strftime("%d")
        url = f"{BASE_API_URL}/daily-congressional-record?y={y}&m={m}&d={d}"
        
        try:
            data = self._fetch_json(url)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return [] # No record for this day
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
                articles_url = issue_detail.get("issue", {}).get("fullIssue", {}).get("articles", {}).get("url")
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
                print(f"Error processing issue {issue_url}: {e}")
                continue
                
        return events

    def _is_relevant(self, article: Dict) -> bool:
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

    def _create_event(self, article: Dict, issue_meta: Dict, section_name: Dict) -> Optional[RawEvent]:
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
            try:
                # We need to be careful about rate limits here too
                resp = requests.get(text_url, headers={"User-Agent": "VA-Signals/1.0"})
                if resp.status_code == 200:
                    raw_html = resp.text
            except Exception as e:
                print(f"Error fetching HTML for {text_url}: {e}")
        
        return RawEvent(
            title=title,
            raw_html=raw_html,
            excerpt=f"Congressional Record ({section_name}) - Pages {start_page}-{article.get('endPage')}",
            url=url,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            metadata={
                "date": date_str,
                "chamber": section_name,
                "volume": vol,
                "issue": iss,
                "pages": f"{start_page}-{article.get('endPage')}",
                "pdf_url": pdf_url,
                "source_id": f"cr-{vol}-{iss}-{start_page}" # Store ID in metadata
            }
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
            chamber_prefix = page[0] if page[0] in ['S', 'H', 'E'] else ''
            refs["citation"] = f"{vol} Cong. Rec. {page}"
            
        return refs
