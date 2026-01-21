"""Tests for state notification formatting."""

import pytest

from src.state.notify import format_state_alert, format_state_digest


class TestFormatStateAlert:
    """Tests for format_state_alert function."""

    def test_empty_input_returns_none(self):
        """Empty list returns None."""
        assert format_state_alert([]) is None
        assert format_state_alert(None) is None

    def test_single_signal_basic(self):
        """Single signal formats correctly."""
        signals = [
            {
                "state": "TX",
                "title": "Texas Veterans Commission suspends PACT Act outreach",
                "url": "https://example.com/article",
                "program": "PACT Act",
                "source_id": "tx_tvc_news",
                "keywords_matched": "suspend",
            }
        ]

        result = format_state_alert(signals)

        assert result is not None
        assert "text" in result
        text = result["text"]

        # Check header
        assert "*State Intelligence Alert*" in text
        # Check state tag
        assert "*[TX]*" in text
        # Check Slack link format
        assert "<https://example.com/article|Texas Veterans Commission suspends PACT Act outreach>" in text
        # Check program
        assert "_PACT Act_" in text
        # Check source
        assert "tx_tvc_news" in text
        # Check triggers
        assert "Triggers: suspend" in text

    def test_multiple_signals(self):
        """Multiple signals format correctly with blank lines between."""
        signals = [
            {
                "state": "TX",
                "title": "Texas Veterans Commission suspends PACT Act outreach",
                "url": "https://example.com/tx-article",
                "program": "PACT Act",
                "source_id": "tx_tvc_news",
                "keywords_matched": "suspend",
            },
            {
                "state": "CA",
                "title": "CalVet reports 30% backlog in toxic exposure claims",
                "url": "https://example.com/ca-article",
                "program": "PACT Act",
                "source_id": "ca_calvet_news",
                "keywords_matched": "backlog",
            },
        ]

        result = format_state_alert(signals)

        assert result is not None
        text = result["text"]

        # Check both states appear
        assert "*[TX]*" in text
        assert "*[CA]*" in text
        # Check both triggers
        assert "Triggers: suspend" in text
        assert "Triggers: backlog" in text

    def test_keywords_as_list(self):
        """Keywords provided as list format correctly."""
        signals = [
            {
                "state": "FL",
                "title": "Florida suspends benefits processing",
                "url": "https://example.com/fl",
                "program": "General",
                "source_id": "fl_dva_news",
                "keywords_matched": ["suspend", "delay", "halt"],
            }
        ]

        result = format_state_alert(signals)

        assert result is not None
        text = result["text"]
        assert "Triggers: suspend, delay, halt" in text

    def test_keywords_as_comma_string(self):
        """Keywords provided as comma-separated string format correctly."""
        signals = [
            {
                "state": "TX",
                "title": "Test signal",
                "url": "https://example.com",
                "program": "General",
                "source_id": "test_source",
                "keywords_matched": "suspend, delay, halt",
            }
        ]

        result = format_state_alert(signals)

        assert result is not None
        text = result["text"]
        assert "Triggers: suspend, delay, halt" in text

    def test_missing_keywords(self):
        """Signal without keywords does not show Triggers line."""
        signals = [
            {
                "state": "TX",
                "title": "Test signal",
                "url": "https://example.com",
                "program": "General",
                "source_id": "test_source",
                "keywords_matched": None,
            }
        ]

        result = format_state_alert(signals)

        assert result is not None
        text = result["text"]
        assert "Triggers:" not in text

    def test_empty_keywords(self):
        """Signal with empty keywords does not show Triggers line."""
        signals = [
            {
                "state": "TX",
                "title": "Test signal",
                "url": "https://example.com",
                "program": "General",
                "source_id": "test_source",
                "keywords_matched": "",
            }
        ]

        result = format_state_alert(signals)

        assert result is not None
        text = result["text"]
        assert "Triggers:" not in text

    def test_missing_program_defaults_to_general(self):
        """Missing program field defaults to 'General'."""
        signals = [
            {
                "state": "TX",
                "title": "Test signal",
                "url": "https://example.com",
                "source_id": "test_source",
            }
        ]

        result = format_state_alert(signals)

        assert result is not None
        text = result["text"]
        assert "_General_" in text

    def test_missing_state_defaults_to_question_marks(self):
        """Missing state field defaults to '??'."""
        signals = [
            {
                "title": "Test signal",
                "url": "https://example.com",
                "source_id": "test_source",
            }
        ]

        result = format_state_alert(signals)

        assert result is not None
        text = result["text"]
        assert "*[??]*" in text

    def test_missing_url_no_link(self):
        """Signal without URL shows title without link formatting."""
        signals = [
            {
                "state": "TX",
                "title": "Test signal without URL",
                "url": "",
                "program": "General",
                "source_id": "test_source",
            }
        ]

        result = format_state_alert(signals)

        assert result is not None
        text = result["text"]
        # Should not have Slack link format
        assert "<|" not in text
        assert "Test signal without URL" in text

    def test_missing_title_defaults_to_unknown(self):
        """Missing title field defaults to 'Unknown'."""
        signals = [
            {
                "state": "TX",
                "url": "https://example.com",
                "source_id": "test_source",
            }
        ]

        result = format_state_alert(signals)

        assert result is not None
        text = result["text"]
        assert "Unknown" in text

    def test_missing_source_id_defaults_to_unknown(self):
        """Missing source_id field defaults to 'unknown'."""
        signals = [
            {
                "state": "TX",
                "title": "Test",
                "url": "https://example.com",
            }
        ]

        result = format_state_alert(signals)

        assert result is not None
        text = result["text"]
        assert "| unknown" in text

    def test_slack_link_format_with_special_characters(self):
        """URL with special characters formats correctly in Slack link."""
        signals = [
            {
                "state": "TX",
                "title": "Test & Title with <special> chars",
                "url": "https://example.com/path?param=value&other=123",
                "program": "General",
                "source_id": "test_source",
            }
        ]

        result = format_state_alert(signals)

        assert result is not None
        text = result["text"]
        # Slack link should contain URL and title
        assert "<https://example.com/path?param=value&other=123|" in text

    def test_format_matches_design_spec(self):
        """Output matches the design spec example format."""
        signals = [
            {
                "state": "Texas",
                "title": "Texas Veterans Commission suspends PACT Act outreach",
                "url": "https://example.com/source",
                "program": "PACT Act",
                "source_id": "Source",
                "keywords_matched": "suspend",
            },
            {
                "state": "California",
                "title": "CalVet reports 30% backlog in toxic exposure claims",
                "url": "https://example.com/source2",
                "program": "PACT Act",
                "source_id": "Source",
                "keywords_matched": "backlog",
            },
        ]

        result = format_state_alert(signals)

        assert result is not None
        text = result["text"]

        # Verify structure matches design spec
        lines = text.split("\n")

        # First line is header
        assert lines[0] == "*State Intelligence Alert*"

        # Second line is blank
        assert lines[1] == ""

        # Check bullet point format
        assert any(line.startswith("• *[Texas]*") for line in lines)
        assert any(line.startswith("• *[California]*") for line in lines)


class TestFormatStateDigest:
    """Tests for format_state_digest function (Task 7.2 placeholder)."""

    def test_returns_none_placeholder(self):
        """Placeholder returns None."""
        # This is a placeholder for Task 7.2
        result = format_state_digest({})
        assert result is None

        result = format_state_digest({"TX": []})
        assert result is None
