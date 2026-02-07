"""Tests for BVA (Board of Veterans' Appeals) decision agent."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from src.oversight.agents.base import RawEvent
from src.oversight.agents.bva import (
    BVA_CITATION_PATTERN,
    BVA_DATE_PATTERN,
    BVA_DOCKET_PATTERN,
    BVA_FULL_DATE_PATTERN,
    BVAAgent,
)


@pytest.fixture
def bva_agent():
    """Create a BVAAgent instance for testing."""
    return BVAAgent()


# Sample HTML for search results page
SAMPLE_SEARCH_HTML = """
<html><body>
<div class="content-block-item result">
  <a href="https://www.va.gov/vetapp25/Files9/A25084198.txt">A25084198.txt</a>
  https://www.va.gov/vetapp25/Files9/A25084198.txt
  The appeal for entitlement to service connection for dizziness is dismissed.
</div>
<div class="content-block-item result">
  <a href="https://www.va.gov/vetapp25/Files10/25012708.txt">25012708.txt</a>
  https://www.va.gov/vetapp25/Files10/25012708.txt
  Service connection for spinal stenosis granted.
</div>
<div class="content-block-item result">
  <a href="https://www.va.gov/vetapp23/Files4/23023720.txt">23023720.txt</a>
  https://www.va.gov/vetapp23/Files4/23023720.txt
  ...percent, but no higher, for a skin disability is granted. REMANDED
</div>
</body></html>
"""

SAMPLE_EMPTY_HTML = """
<html><body>
<div>No results found.</div>
</body></html>
"""

SAMPLE_DECISION_TEXT = """Citation Nr: A25084198
Decision Date: 09/30/25\tArchive Date: 09/30/25

DOCKET NO. 240901-469829
DATE: September 30, 2025

ORDER

The appeal for entitlement to service connection for dizziness is dismissed.
The appeal for entitlement to service connection for hypertension is dismissed.

REMANDED

Entitlement to an increased rating for PTSD is remanded.

REASONS FOR REMAND

The Veteran served on active duty from January 1990 to December 1995.
"""


class TestBVAAgentBasics:
    """Basic tests for BVAAgent."""

    def test_source_type(self, bva_agent):
        """Agent has correct source type."""
        assert bva_agent.source_type == "bva"

    def test_default_urls(self, bva_agent):
        """Agent has correct default search URL and affiliate."""
        assert "search.usa.gov" in bva_agent.search_url
        assert bva_agent.affiliate == "bvadecisions"

    def test_custom_urls(self):
        """Agent accepts custom search URL and affiliate."""
        agent = BVAAgent(
            search_url="https://custom.search.url",
            affiliate="custom_affiliate",
        )
        assert agent.search_url == "https://custom.search.url"
        assert agent.affiliate == "custom_affiliate"


class TestBVAAgentFetchNew:
    """Tests for BVAAgent.fetch_new method."""

    @patch("src.oversight.agents.bva.requests.get")
    def test_fetch_new_returns_events(self, mock_get, bva_agent):
        """fetch_new returns BVA decision events from search results."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = SAMPLE_SEARCH_HTML
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        events = bva_agent.fetch_new(since=None)

        assert len(events) > 0
        assert all(isinstance(e, RawEvent) for e in events)

    @patch("src.oversight.agents.bva.requests.get")
    def test_fetch_new_extracts_citation(self, mock_get, bva_agent):
        """fetch_new extracts citation number from result URL."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = SAMPLE_SEARCH_HTML
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        events = bva_agent.fetch_new(since=None)

        citations = [e.metadata.get("citation_nr") for e in events]
        assert "A25084198" in citations or "25012708" in citations

    @patch("src.oversight.agents.bva.requests.get")
    def test_fetch_new_extracts_year(self, mock_get, bva_agent):
        """fetch_new extracts year from vetapp URL path."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = SAMPLE_SEARCH_HTML
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        events = bva_agent.fetch_new(since=None)

        years = [e.metadata.get("year") for e in events]
        assert "2025" in years

    @patch("src.oversight.agents.bva.requests.get")
    def test_fetch_new_deduplicates_across_queries(self, mock_get, bva_agent):
        """fetch_new deduplicates results across multiple queries."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = SAMPLE_SEARCH_HTML
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        events = bva_agent.fetch_new(since=None)

        urls = [e.url for e in events]
        assert len(urls) == len(set(urls)), "Duplicate URLs in results"

    @patch("src.oversight.agents.bva.requests.get")
    def test_fetch_new_since_filters_old_years(self, mock_get, bva_agent):
        """fetch_new filters out decisions from years before since."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = SAMPLE_SEARCH_HTML
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        since = datetime(2025, 1, 1, tzinfo=UTC)
        events = bva_agent.fetch_new(since=since)

        # 2023 decision should be filtered out
        for event in events:
            year = event.metadata.get("year")
            if year:
                assert int(year) >= 2025

    @patch("src.oversight.agents.bva.requests.get")
    def test_fetch_new_empty_results(self, mock_get, bva_agent):
        """fetch_new returns empty list when no results found."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = SAMPLE_EMPTY_HTML
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        events = bva_agent.fetch_new(since=None)

        assert events == []

    @patch("src.oversight.agents.bva.requests.get")
    def test_fetch_new_handles_http_error(self, mock_get, bva_agent):
        """fetch_new handles HTTP errors gracefully."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("503 Service Unavailable")
        mock_get.return_value = mock_resp

        # Should not raise, just return empty
        events = bva_agent.fetch_new(since=None)
        assert events == []

    @patch("src.oversight.agents.bva.requests.get")
    def test_fetch_new_handles_connection_error(self, mock_get, bva_agent):
        """fetch_new handles connection errors gracefully."""
        mock_get.side_effect = ConnectionError("Connection refused")

        events = bva_agent.fetch_new(since=None)
        assert events == []

    @patch("src.oversight.agents.bva.requests.get")
    def test_fetch_new_sets_fetched_at(self, mock_get, bva_agent):
        """fetch_new sets fetched_at timestamp on events."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = SAMPLE_SEARCH_HTML
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        events = bva_agent.fetch_new(since=None)

        for event in events:
            assert event.fetched_at is not None
            assert "T" in event.fetched_at

    @patch("src.oversight.agents.bva.requests.get")
    def test_fetch_new_sets_title(self, mock_get, bva_agent):
        """fetch_new sets title with BVA Decision prefix."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = SAMPLE_SEARCH_HTML
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        events = bva_agent.fetch_new(since=None)

        for event in events:
            assert event.title.startswith("BVA Decision")

    @patch("src.oversight.agents.bva.requests.get")
    def test_fetch_new_skips_non_txt_links(self, mock_get, bva_agent):
        """fetch_new skips links that are not .txt files."""
        html = """
        <html><body>
        <div class="content-block-item result">
          <a href="https://example.com/page.html">Not a decision</a>
        </div>
        <div class="content-block-item result">
          <a href="https://www.va.gov/vetapp25/Files9/A25084198.txt">A25084198.txt</a>
          Decision text here.
        </div>
        </body></html>
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = html
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        events = bva_agent.fetch_new(since=None)

        for event in events:
            assert event.url.endswith(".txt")


class TestBVAAgentBackfill:
    """Tests for BVAAgent.backfill method."""

    @patch("src.oversight.agents.bva.requests.get")
    def test_backfill_returns_events_in_range(self, mock_get, bva_agent):
        """backfill returns events within date range."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = SAMPLE_SEARCH_HTML
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        start = datetime(2025, 1, 1, tzinfo=UTC)
        end = datetime(2025, 12, 31, tzinfo=UTC)

        events = bva_agent.backfill(start, end)
        assert isinstance(events, list)

    @patch("src.oversight.agents.bva.requests.get")
    def test_backfill_returns_list(self, mock_get, bva_agent):
        """backfill always returns a list."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = SAMPLE_EMPTY_HTML
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        start = datetime(2025, 1, 1, tzinfo=UTC)
        end = datetime(2025, 12, 31, tzinfo=UTC)

        events = bva_agent.backfill(start, end)
        assert isinstance(events, list)


class TestBVAAgentFetchDecisionDetail:
    """Tests for BVAAgent.fetch_decision_detail method."""

    @patch("src.oversight.agents.bva.requests.get")
    def test_parses_citation_nr(self, mock_get, bva_agent):
        """Parses citation number from decision text."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = SAMPLE_DECISION_TEXT
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        detail = bva_agent.fetch_decision_detail("https://va.gov/vetapp25/Files9/A25084198.txt")

        assert detail is not None
        assert detail["citation_nr"] == "A25084198"

    @patch("src.oversight.agents.bva.requests.get")
    def test_parses_decision_date(self, mock_get, bva_agent):
        """Parses decision date from header."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = SAMPLE_DECISION_TEXT
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        detail = bva_agent.fetch_decision_detail("https://va.gov/decision.txt")

        assert detail["decision_date_raw"] == "09/30/25"

    @patch("src.oversight.agents.bva.requests.get")
    def test_parses_full_date(self, mock_get, bva_agent):
        """Parses full date from DATE: line."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = SAMPLE_DECISION_TEXT
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        detail = bva_agent.fetch_decision_detail("https://va.gov/decision.txt")

        assert detail["decision_date_full"] == "September 30, 2025"

    @patch("src.oversight.agents.bva.requests.get")
    def test_parses_docket_number(self, mock_get, bva_agent):
        """Parses docket number from decision text."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = SAMPLE_DECISION_TEXT
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        detail = bva_agent.fetch_decision_detail("https://va.gov/decision.txt")

        assert detail["docket_no"] == "240901-469829"

    @patch("src.oversight.agents.bva.requests.get")
    def test_parses_decision_types(self, mock_get, bva_agent):
        """Parses decision outcome types (dismissed, remanded, etc.)."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = SAMPLE_DECISION_TEXT
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        detail = bva_agent.fetch_decision_detail("https://va.gov/decision.txt")

        assert "dismissed" in detail["decision_types"]

    @patch("src.oversight.agents.bva.requests.get")
    def test_handles_http_error(self, mock_get, bva_agent):
        """Returns None when HTTP request fails."""
        mock_get.side_effect = Exception("Connection failed")

        detail = bva_agent.fetch_decision_detail("https://va.gov/decision.txt")

        assert detail is None

    @patch("src.oversight.agents.bva.requests.get")
    def test_truncates_full_text(self, mock_get, bva_agent):
        """Truncates full text to 5000 characters."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "A" * 10000
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        detail = bva_agent.fetch_decision_detail("https://va.gov/decision.txt")

        assert detail is not None
        assert len(detail["full_text"]) == 5000


class TestBVAAgentExtractTimestamps:
    """Tests for BVAAgent.extract_timestamps method."""

    def test_extract_from_full_date(self, bva_agent):
        """Extracts timestamp from decision_date_full metadata."""
        raw = RawEvent(
            url="https://va.gov/vetapp25/Files9/A25084198.txt",
            title="BVA Decision A25084198",
            raw_html="",
            fetched_at="2026-01-20T15:00:00Z",
            metadata={"decision_date_full": "September 30, 2025"},
        )

        result = bva_agent.extract_timestamps(raw)

        assert result.pub_timestamp is not None
        assert "2025-09-30" in result.pub_timestamp
        assert result.pub_precision == "date"
        assert result.pub_source == "extracted"

    def test_extract_from_raw_date(self, bva_agent):
        """Extracts timestamp from decision_date_raw (MM/DD/YY) metadata."""
        raw = RawEvent(
            url="https://va.gov/vetapp25/Files9/A25084198.txt",
            title="BVA Decision A25084198",
            raw_html="",
            fetched_at="2026-01-20T15:00:00Z",
            metadata={"decision_date_raw": "09/30/25"},
        )

        result = bva_agent.extract_timestamps(raw)

        assert result.pub_timestamp is not None
        assert "2025-09-30" in result.pub_timestamp
        assert result.pub_precision == "date"
        assert result.pub_source == "extracted"

    def test_fallback_to_year(self, bva_agent):
        """Falls back to year from URL when no date metadata."""
        raw = RawEvent(
            url="https://va.gov/vetapp25/Files9/A25084198.txt",
            title="BVA Decision A25084198",
            raw_html="",
            fetched_at="2026-01-20T15:00:00Z",
            metadata={"year": "2025"},
        )

        result = bva_agent.extract_timestamps(raw)

        assert result.pub_timestamp is not None
        assert "2025-01-01" in result.pub_timestamp
        assert result.pub_precision == "month"
        assert result.pub_source == "inferred"

    def test_missing_all_dates(self, bva_agent):
        """Returns unknown when no date information available."""
        raw = RawEvent(
            url="https://example.com/unknown.txt",
            title="BVA Decision Unknown",
            raw_html="",
            fetched_at="2026-01-20T15:00:00Z",
            metadata={},
        )

        result = bva_agent.extract_timestamps(raw)

        assert result.pub_timestamp is None
        assert result.pub_precision == "unknown"
        assert result.pub_source == "missing"

    def test_prefers_full_date_over_raw(self, bva_agent):
        """Prefers decision_date_full over decision_date_raw."""
        raw = RawEvent(
            url="https://va.gov/vetapp25/Files9/A25084198.txt",
            title="BVA Decision A25084198",
            raw_html="",
            fetched_at="2026-01-20T15:00:00Z",
            metadata={
                "decision_date_full": "October 15, 2025",
                "decision_date_raw": "09/30/25",
            },
        )

        result = bva_agent.extract_timestamps(raw)

        assert "2025-10-15" in result.pub_timestamp


class TestBVAAgentExtractCanonicalRefs:
    """Tests for BVAAgent.extract_canonical_refs method."""

    def test_extract_citation(self, bva_agent):
        """Extracts BVA citation number."""
        raw = RawEvent(
            url="https://va.gov/vetapp25/Files9/A25084198.txt",
            title="BVA Decision A25084198",
            raw_html="",
            fetched_at="2026-01-20T15:00:00Z",
            metadata={"citation_nr": "A25084198"},
        )

        refs = bva_agent.extract_canonical_refs(raw)

        assert refs.get("bva_citation") == "A25084198"

    def test_extract_docket(self, bva_agent):
        """Extracts BVA docket number."""
        raw = RawEvent(
            url="https://va.gov/vetapp25/Files9/A25084198.txt",
            title="BVA Decision A25084198",
            raw_html="",
            fetched_at="2026-01-20T15:00:00Z",
            metadata={"docket_no": "240901-469829"},
        )

        refs = bva_agent.extract_canonical_refs(raw)

        assert refs.get("bva_docket") == "240901-469829"

    def test_extract_decision_types(self, bva_agent):
        """Extracts decision types from metadata."""
        raw = RawEvent(
            url="https://va.gov/vetapp25/Files9/A25084198.txt",
            title="BVA Decision A25084198",
            raw_html="",
            fetched_at="2026-01-20T15:00:00Z",
            metadata={"decision_types": ["dismissed", "remanded"]},
        )

        refs = bva_agent.extract_canonical_refs(raw)

        assert refs.get("decision_types") == ["dismissed", "remanded"]

    def test_empty_metadata_returns_empty(self, bva_agent):
        """Returns empty dict when no metadata present."""
        raw = RawEvent(
            url="https://example.com/unknown.txt",
            title="BVA Decision",
            raw_html="",
            fetched_at="2026-01-20T15:00:00Z",
            metadata={},
        )

        refs = bva_agent.extract_canonical_refs(raw)

        assert refs == {}


class TestBVAPatterns:
    """Tests for BVA regex patterns."""

    def test_citation_pattern_legacy(self):
        """Matches legacy citation format (YYMMNNNNN)."""
        match = BVA_CITATION_PATTERN.match("23023720")
        assert match is not None
        assert match.group(1) == "23023720"

    def test_citation_pattern_ama(self):
        """Matches AMA citation format (AYYMMNNNN)."""
        match = BVA_CITATION_PATTERN.match("A25084198")
        assert match is not None
        assert match.group(1) == "A25084198"

    def test_citation_pattern_no_match(self):
        """Does not match invalid citation format."""
        match = BVA_CITATION_PATTERN.match("ABCDEF")
        assert match is None

    def test_date_pattern_matches(self):
        """Matches Decision Date header format."""
        text = "Decision Date: 09/30/25\tArchive Date: 09/30/25"
        match = BVA_DATE_PATTERN.search(text)
        assert match is not None
        assert match.group(1) == "09/30/25"

    def test_docket_pattern_matches(self):
        """Matches DOCKET NO. format."""
        text = "DOCKET NO. 240901-469829"
        match = BVA_DOCKET_PATTERN.search(text)
        assert match is not None
        assert match.group(1) == "240901-469829"

    def test_full_date_pattern_matches(self):
        """Matches full date format."""
        text = "DATE: September 30, 2025"
        match = BVA_FULL_DATE_PATTERN.search(text)
        assert match is not None
        assert match.group(1) == "September 30, 2025"


class TestBVAAgentParseDate:
    """Tests for BVAAgent._parse_date method."""

    def test_parse_mm_dd_yy(self, bva_agent):
        """Parses MM/DD/YY format."""
        dt = bva_agent._parse_date("09/30/25")
        assert dt is not None
        assert dt.year == 2025
        assert dt.month == 9
        assert dt.day == 30

    def test_parse_mm_dd_yyyy(self, bva_agent):
        """Parses MM/DD/YYYY format."""
        dt = bva_agent._parse_date("09/30/2025")
        assert dt is not None
        assert dt.year == 2025

    def test_parse_iso_format(self, bva_agent):
        """Parses YYYY-MM-DD format."""
        dt = bva_agent._parse_date("2025-09-30")
        assert dt is not None
        assert dt.year == 2025

    def test_parse_full_month_name(self, bva_agent):
        """Parses 'Month DD, YYYY' format."""
        dt = bva_agent._parse_date("September 30, 2025")
        assert dt is not None
        assert dt.year == 2025
        assert dt.month == 9

    def test_parse_abbreviated_month(self, bva_agent):
        """Parses 'Mon DD, YYYY' format."""
        dt = bva_agent._parse_date("Sep 30, 2025")
        assert dt is not None
        assert dt.year == 2025

    def test_parse_empty_string(self, bva_agent):
        """Returns None for empty string."""
        assert bva_agent._parse_date("") is None

    def test_parse_none(self, bva_agent):
        """Returns None for None input."""
        assert bva_agent._parse_date(None) is None

    def test_parse_invalid_format(self, bva_agent):
        """Returns None for unrecognized format."""
        assert bva_agent._parse_date("not a date") is None

    def test_parse_has_timezone(self, bva_agent):
        """Parsed dates have UTC timezone."""
        dt = bva_agent._parse_date("09/30/2025")
        assert dt.tzinfo == UTC


class TestBVAAgentRegistration:
    """Tests for BVA agent registration in the runner."""

    def test_bva_in_agent_registry(self):
        """BVA agent is registered in AGENT_REGISTRY."""
        from src.oversight.runner import AGENT_REGISTRY

        assert "bva" in AGENT_REGISTRY

    def test_bva_registry_is_correct_class(self):
        """BVA agent registry entry points to BVAAgent class."""
        from src.oversight.runner import AGENT_REGISTRY

        assert AGENT_REGISTRY["bva"] is BVAAgent

    def test_bva_in_init_exports(self):
        """BVAAgent is exported from agents __init__."""
        from src.oversight.agents import BVAAgent as ExportedBVA

        assert ExportedBVA is BVAAgent

    def test_bva_instantiation(self):
        """BVAAgent can be instantiated from registry."""
        from src.oversight.runner import AGENT_REGISTRY

        agent = AGENT_REGISTRY["bva"]()
        assert agent.source_type == "bva"
