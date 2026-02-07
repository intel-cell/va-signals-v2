"""Tests for LOE1 hardened fetch error handling.

Validates that:
1. CR agent _create_event handles HTTP failures gracefully
2. sync_va_hearings records errors on exception
3. All fetch modules have a logger attribute
"""

import logging
from unittest.mock import MagicMock, patch

# ── Test 1: CR agent _create_event handles HTTP failures ─────────


class TestCRAgentCreateEvent:
    """Test that _create_event handles _fetch_html failures gracefully."""

    @patch("src.oversight.agents.congressional_record.get_env_or_keychain", return_value="fake-key")
    def test_create_event_returns_event_when_fetch_html_fails(self, _mock_key):
        from src.oversight.agents.congressional_record import CongressionalRecordAgent

        agent = CongressionalRecordAgent()

        # Mock _fetch_html to return None (simulating failure)
        agent._fetch_html = MagicMock(return_value=None)

        article = {
            "title": "Veterans Affairs Budget Discussion",
            "text": [
                {"type": "Formatted Text", "url": "https://example.com/text.htm"},
                {"type": "PDF", "url": "https://example.com/doc.pdf"},
            ],
            "startPage": "S100",
            "endPage": "S105",
        }
        issue_meta = {
            "volumeNumber": "172",
            "issueNumber": "10",
            "issueDate": "2026-01-29T05:00:00Z",
        }

        event = agent._create_event(article, issue_meta, "Senate")

        # Should still return an event even though HTML fetch failed
        assert event is not None
        assert event.title == "Veterans Affairs Budget Discussion"
        assert event.raw_html == ""  # Empty because fetch failed
        agent._fetch_html.assert_called_once()

    @patch("src.oversight.agents.congressional_record.get_env_or_keychain", return_value="fake-key")
    def test_create_event_returns_none_without_url(self, _mock_key):
        from src.oversight.agents.congressional_record import CongressionalRecordAgent

        agent = CongressionalRecordAgent()

        article = {
            "title": "Some Article",
            "text": [],  # No text URLs
        }
        issue_meta = {"volumeNumber": "172", "issueNumber": "10"}

        event = agent._create_event(article, issue_meta, "Senate")
        assert event is None

    @patch("src.oversight.agents.congressional_record.get_env_or_keychain", return_value="fake-key")
    def test_create_event_returns_none_without_title(self, _mock_key):
        from src.oversight.agents.congressional_record import CongressionalRecordAgent

        agent = CongressionalRecordAgent()

        article = {"text": [{"type": "PDF", "url": "https://example.com/doc.pdf"}]}
        issue_meta = {"volumeNumber": "172", "issueNumber": "10"}

        event = agent._create_event(article, issue_meta, "Senate")
        assert event is None

    @patch("src.oversight.agents.congressional_record.get_env_or_keychain", return_value="fake-key")
    def test_create_event_uses_html_when_fetch_succeeds(self, _mock_key):
        from src.oversight.agents.congressional_record import CongressionalRecordAgent

        agent = CongressionalRecordAgent()
        agent._fetch_html = MagicMock(return_value="<html>content</html>")

        article = {
            "title": "VA Discussion",
            "text": [{"type": "Formatted Text", "url": "https://example.com/text.htm"}],
            "startPage": "H200",
            "endPage": "H210",
        }
        issue_meta = {
            "volumeNumber": "172",
            "issueNumber": "10",
            "issueDate": "2026-01-29",
        }

        event = agent._create_event(article, issue_meta, "House")
        assert event is not None
        assert event.raw_html == "<html>content</html>"


# ── Test 2: sync_va_hearings records errors ──────────────────────


class TestSyncVAHearingsErrorRecording:
    """Test that sync_va_hearings records errors when exceptions occur."""

    @patch("src.fetch_hearings.fetch_committee_meetings")
    def test_records_error_when_chamber_fetch_fails(self, mock_fetch):
        from src.fetch_hearings import sync_va_hearings

        mock_fetch.side_effect = RuntimeError("API connection failed")

        stats = sync_va_hearings(congress=119, limit=10, dry_run=True)

        # Should record errors for both chambers
        assert len(stats["errors"]) == 2
        assert "house" in stats["errors"][0].lower() or "API connection" in stats["errors"][0]

    @patch("src.fetch_hearings.fetch_meeting_details")
    @patch("src.fetch_hearings.fetch_committee_meetings")
    def test_records_error_when_meeting_details_fail(self, mock_meetings, mock_details):
        from src.fetch_hearings import sync_va_hearings

        # Return meetings for one chamber, empty for another
        mock_meetings.side_effect = [
            [{"eventId": "evt-001"}, {"eventId": "evt-002"}],
            [],  # Senate returns empty
        ]
        # Details fetch fails
        mock_details.side_effect = RuntimeError("Detail fetch failed")

        stats = sync_va_hearings(congress=119, limit=10, dry_run=True)

        # Should have recorded the errors
        assert len(stats["errors"]) >= 2
        assert any("evt-001" in e for e in stats["errors"])


# ── Test 3: All fetch modules have a logger attribute ────────────


class TestFetchModulesHaveLogger:
    """Verify all fetch modules define a module-level logger."""

    def test_fetch_bills_has_logger(self):
        from src import fetch_bills

        assert hasattr(fetch_bills, "logger")
        assert isinstance(fetch_bills.logger, logging.Logger)

    def test_fetch_hearings_has_logger(self):
        from src import fetch_hearings

        assert hasattr(fetch_hearings, "logger")
        assert isinstance(fetch_hearings.logger, logging.Logger)

    def test_fetch_whitehouse_has_logger(self):
        from src import fetch_whitehouse

        assert hasattr(fetch_whitehouse, "logger")
        assert isinstance(fetch_whitehouse.logger, logging.Logger)

    def test_fetch_reginfo_pra_has_logger(self):
        from src import fetch_reginfo_pra

        assert hasattr(fetch_reginfo_pra, "logger")
        assert isinstance(fetch_reginfo_pra.logger, logging.Logger)

    def test_fetch_omb_internal_drop_has_logger(self):
        from src import fetch_omb_internal_drop

        assert hasattr(fetch_omb_internal_drop, "logger")
        assert isinstance(fetch_omb_internal_drop.logger, logging.Logger)

    def test_congressional_record_has_logger(self):
        from src.oversight.agents import congressional_record

        assert hasattr(congressional_record, "logger")
        assert isinstance(congressional_record.logger, logging.Logger)
