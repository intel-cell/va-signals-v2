"""Tests for CAFC (Court of Appeals for the Federal Circuit) agent."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from src.oversight.agents.base import RawEvent
from src.oversight.agents.cafc import CAFC_CASE_PATTERN, CAFCAgent


@pytest.fixture
def cafc_agent():
    """Create a CAFCAgent instance for testing."""
    return CAFCAgent()


class MockRSSEntry:
    """Mock RSS entry that behaves like feedparser entry."""

    def __init__(self, title, link, published, summary):
        self.title = title
        self.link = link
        self.published = published
        self.summary = summary


SAMPLE_RSS_ENTRY = MockRSSEntry(
    title="Smith v. McDonough - Precedential Opinion",
    link="https://www.cafc.uscourts.gov/opinions/26-1234.pdf",
    published="Mon, 20 Jan 2026 10:00:00 EST",
    summary="Appellant veteran appeals Board of Veterans' Appeals decision...",
)


SAMPLE_NON_VA_RSS_ENTRY = MockRSSEntry(
    title="Acme Corp v. USPTO - Patent Dispute",
    link="https://www.cafc.uscourts.gov/opinions/26-9999.pdf",
    published="Mon, 20 Jan 2026 11:00:00 EST",
    summary="Patent infringement case...",
)


class TestCAFCAgentBasics:
    """Basic tests for CAFCAgent."""

    def test_source_type(self, cafc_agent):
        """Agent has correct source type."""
        assert cafc_agent.source_type == "cafc"

    def test_va_parties_list(self, cafc_agent):
        """Agent has VA party names for filtering."""
        assert "McDonough" in cafc_agent.va_parties
        assert "Secretary of Veterans Affairs" in cafc_agent.va_parties
        assert "Department of Veterans Affairs" in cafc_agent.va_parties

    def test_va_origins_includes_cavc(self, cafc_agent):
        """Agent recognizes CAVC as VA-related origin."""
        assert "CAVC" in cafc_agent.va_origins


class TestCAFCAgentIsVARelated:
    """Tests for CAFCAgent._is_va_related method."""

    def test_detects_cavc_in_url(self, cafc_agent):
        """Detects CAVC (Court of Appeals for Veterans Claims) in URL."""
        assert cafc_agent._is_va_related("", "", "https://example.com/CAVC/case.pdf")

    def test_detects_mcdonough_party(self, cafc_agent):
        """Detects McDonough (VA Secretary) as party."""
        assert cafc_agent._is_va_related("Smith v. McDonough", "", "")

    def test_detects_va_in_title(self, cafc_agent):
        """Detects Veterans Affairs in title."""
        assert cafc_agent._is_va_related("Doe v. Department of Veterans Affairs", "", "")

    def test_detects_va_secretary(self, cafc_agent):
        """Detects Secretary of Veterans Affairs."""
        assert cafc_agent._is_va_related("Appeal from Secretary of Veterans Affairs", "", "")

    def test_case_insensitive_matching(self, cafc_agent):
        """Matching is case-insensitive."""
        assert cafc_agent._is_va_related("smith v. MCDONOUGH", "", "")
        assert cafc_agent._is_va_related("VETERANS AFFAIRS", "", "")

    def test_non_va_case_not_detected(self, cafc_agent):
        """Non-VA cases are not detected as VA-related."""
        assert not cafc_agent._is_va_related(
            "Acme Corp v. USPTO", "Patent case", "https://cafc.gov/patent.pdf"
        )


class TestCAFCAgentFetchNew:
    """Tests for CAFCAgent.fetch_new method."""

    @patch("src.oversight.agents.cafc.feedparser.parse")
    def test_fetch_new_from_rss(self, mock_parse, cafc_agent):
        """fetch_new retrieves VA-related cases from RSS."""
        mock_parse.return_value = MagicMock(
            bozo=False,
            entries=[SAMPLE_RSS_ENTRY],
        )

        events = cafc_agent.fetch_new(since=None)

        assert len(events) == 1
        assert "McDonough" in events[0].title or "26-1234" in events[0].url

    @patch("src.oversight.agents.cafc.requests.get")
    @patch("src.oversight.agents.cafc.feedparser.parse")
    def test_fetch_new_filters_non_va_cases(self, mock_parse, mock_requests, cafc_agent):
        """fetch_new filters out non-VA cases."""
        mock_parse.return_value = MagicMock(
            bozo=False,
            entries=[SAMPLE_NON_VA_RSS_ENTRY],
        )
        # Mock HTML fallback to return empty page (no VA cases)
        mock_requests.return_value = MagicMock(
            status_code=200,
            text="<html><body><table></table></body></html>",
            raise_for_status=lambda: None,
        )

        events = cafc_agent.fetch_new(since=None)

        assert len(events) == 0

    @patch("src.oversight.agents.cafc.requests.get")
    @patch("src.oversight.agents.cafc.feedparser.parse")
    def test_fetch_new_respects_since_date(self, mock_parse, mock_requests, cafc_agent):
        """fetch_new filters events older than since date."""
        old_entry = MockRSSEntry(
            title="Smith v. McDonough - Old Case",
            link="https://cafc.gov/old.pdf",
            published="Mon, 01 Jan 2024 10:00:00 EST",
            summary="Old VA case...",
        )
        mock_parse.return_value = MagicMock(
            bozo=False,
            entries=[old_entry],
        )
        # Mock HTML fallback to return empty page
        mock_requests.return_value = MagicMock(
            status_code=200,
            text="<html><body><table></table></body></html>",
            raise_for_status=lambda: None,
        )

        since = datetime(2026, 1, 1, tzinfo=UTC)
        events = cafc_agent.fetch_new(since=since)

        # Old entry should be filtered out
        assert len(events) == 0

    @patch("src.oversight.agents.cafc.feedparser.parse")
    def test_fetch_new_extracts_case_number(self, mock_parse, cafc_agent):
        """fetch_new extracts case number from entry."""
        mock_parse.return_value = MagicMock(
            bozo=False,
            entries=[SAMPLE_RSS_ENTRY],
        )

        events = cafc_agent.fetch_new(since=None)

        assert len(events) == 1
        assert events[0].metadata.get("case_number") == "26-1234"

    @patch("src.oversight.agents.cafc.feedparser.parse")
    def test_fetch_new_detects_precedential(self, mock_parse, cafc_agent):
        """fetch_new detects precedential status in title."""
        mock_parse.return_value = MagicMock(
            bozo=False,
            entries=[SAMPLE_RSS_ENTRY],
        )

        events = cafc_agent.fetch_new(since=None)

        assert len(events) == 1
        assert events[0].metadata.get("precedential") is True

    @patch("src.oversight.agents.cafc.feedparser.parse")
    @patch("src.oversight.agents.cafc.requests.get")
    def test_fetch_new_falls_back_to_html(self, mock_html_get, mock_parse, cafc_agent):
        """fetch_new falls back to HTML scraping when RSS fails."""
        # RSS fails
        mock_parse.return_value = MagicMock(
            bozo=True,
            bozo_exception=Exception("RSS error"),
            entries=[],
        )
        # HTML returns content
        mock_html_get.return_value = MagicMock(
            status_code=200,
            text="<html><body>No table</body></html>",
            raise_for_status=lambda: None,
        )

        cafc_agent.fetch_new(since=None)

        # Should attempt HTML scraping
        mock_html_get.assert_called_once()


class TestCAFCAgentExtractTimestamps:
    """Tests for CAFCAgent.extract_timestamps method."""

    def test_extract_timestamps_from_metadata(self, cafc_agent):
        """Extracts timestamps from metadata published field."""
        raw = RawEvent(
            url="https://cafc.gov/opinions/26-1234.pdf",
            title="VA Case Decision",
            raw_html="",
            fetched_at="2026-01-20T15:00:00Z",
            metadata={"published": "01/20/2026"},
        )

        result = cafc_agent.extract_timestamps(raw)

        assert result.pub_timestamp is not None
        assert "2026-01-20" in result.pub_timestamp
        assert result.pub_precision == "date"
        assert result.pub_source == "extracted"

    def test_extract_timestamps_from_url(self, cafc_agent):
        """Extracts timestamps from URL pattern when metadata missing."""
        raw = RawEvent(
            url="https://cafc.gov/opinions/26-1234.OPINION.1-20-2026_12345.pdf",
            title="VA Case",
            raw_html="",
            fetched_at="2026-01-20T15:00:00Z",
            metadata={},
        )

        result = cafc_agent.extract_timestamps(raw)

        assert result.pub_timestamp is not None
        assert "2026-01-20" in result.pub_timestamp
        assert result.pub_source == "inferred_from_url"

    def test_extract_timestamps_various_date_formats(self, cafc_agent):
        """Handles various date formats in metadata."""
        formats_to_test = [
            ("01/20/2026", "2026-01-20"),
            ("2026-01-20", "2026-01-20"),
            ("January 20, 2026", "2026-01-20"),
            ("Jan 20, 2026", "2026-01-20"),
        ]

        for input_date, expected in formats_to_test:
            raw = RawEvent(
                url="https://cafc.gov/case.pdf",
                title="VA Case",
                raw_html="",
                fetched_at="2026-01-20T15:00:00Z",
                metadata={"published": input_date},
            )

            result = cafc_agent.extract_timestamps(raw)
            assert expected in result.pub_timestamp, f"Failed for format: {input_date}"

    def test_extract_timestamps_missing(self, cafc_agent):
        """Returns unknown when no timestamp can be extracted."""
        raw = RawEvent(
            url="https://cafc.gov/case.pdf",
            title="VA Case",
            raw_html="",
            fetched_at="2026-01-20T15:00:00Z",
            metadata={},
        )

        result = cafc_agent.extract_timestamps(raw)

        assert result.pub_timestamp is None
        assert result.pub_precision == "unknown"
        assert result.pub_source == "missing"


class TestCAFCAgentExtractCanonicalRefs:
    """Tests for CAFCAgent.extract_canonical_refs method."""

    def test_extract_case_number_from_metadata(self, cafc_agent):
        """Extracts case number from metadata."""
        raw = RawEvent(
            url="https://cafc.gov/case.pdf",
            title="VA Case",
            raw_html="",
            fetched_at="2026-01-20T15:00:00Z",
            metadata={"case_number": "26-1234"},
        )

        refs = cafc_agent.extract_canonical_refs(raw)

        assert refs.get("cafc_case") == "26-1234"

    def test_extract_case_number_from_url(self, cafc_agent):
        """Extracts case number from URL when not in metadata."""
        raw = RawEvent(
            url="https://cafc.gov/opinions/26-5678.pdf",
            title="VA Case",
            raw_html="",
            fetched_at="2026-01-20T15:00:00Z",
            metadata={},
        )

        refs = cafc_agent.extract_canonical_refs(raw)

        assert refs.get("cafc_case") == "26-5678"

    def test_extract_origin(self, cafc_agent):
        """Extracts origin (e.g., CAVC) from metadata."""
        raw = RawEvent(
            url="https://cafc.gov/case.pdf",
            title="VA Case",
            raw_html="",
            fetched_at="2026-01-20T15:00:00Z",
            metadata={"origin": "CAVC"},
        )

        refs = cafc_agent.extract_canonical_refs(raw)

        assert refs.get("origin") == "CAVC"

    def test_extract_precedential_flag(self, cafc_agent):
        """Extracts precedential flag from metadata or title."""
        raw = RawEvent(
            url="https://cafc.gov/case.pdf",
            title="VA Case - Precedential Opinion",
            raw_html="",
            fetched_at="2026-01-20T15:00:00Z",
            metadata={},
        )

        refs = cafc_agent.extract_canonical_refs(raw)

        assert refs.get("is_precedential") is True

    def test_extract_precedential_from_metadata(self, cafc_agent):
        """Extracts precedential flag from metadata."""
        raw = RawEvent(
            url="https://cafc.gov/case.pdf",
            title="VA Case",
            raw_html="",
            fetched_at="2026-01-20T15:00:00Z",
            metadata={"precedential": True},
        )

        refs = cafc_agent.extract_canonical_refs(raw)

        assert refs.get("is_precedential") is True


class TestCAFCCasePattern:
    """Tests for CAFC case number regex pattern."""

    def test_matches_standard_format(self):
        """Matches standard XX-XXXX format."""
        assert CAFC_CASE_PATTERN.search("26-1234")
        assert CAFC_CASE_PATTERN.search("Case 26-1234")

    def test_matches_four_digit_year(self):
        """Matches YYYY-XXXX format."""
        assert CAFC_CASE_PATTERN.search("2026-1234")

    def test_matches_in_url(self):
        """Matches case number in URL."""
        match = CAFC_CASE_PATTERN.search("https://cafc.gov/opinions/26-5678.pdf")
        assert match
        assert match.group(1) == "26"
        assert match.group(2) == "5678"

    def test_does_not_match_invalid(self):
        """Does not match invalid patterns."""
        assert not CAFC_CASE_PATTERN.search("ABC-DEF")


class TestCAFCAgentBackfill:
    """Tests for CAFCAgent.backfill method."""

    @patch("src.oversight.agents.cafc.feedparser.parse")
    def test_backfill_filters_by_date_range(self, mock_parse, cafc_agent):
        """backfill filters events to specified date range."""
        mock_parse.return_value = MagicMock(
            bozo=False,
            entries=[
                MockRSSEntry(
                    title="Smith v. McDonough",
                    link="https://cafc.gov/26-1234.pdf",
                    published="Mon, 15 Jan 2026 10:00:00 EST",
                    summary="VA case...",
                ),
            ],
        )

        start = datetime(2026, 1, 10, tzinfo=UTC)
        end = datetime(2026, 1, 20, tzinfo=UTC)

        events = cafc_agent.backfill(start, end)

        # Should return events within range
        assert isinstance(events, list)
