"""Tests for state digest generation."""

import argparse
from unittest.mock import patch

from src.state.digest import _send_digest_email, generate_weekly_digest, main


class TestGenerateWeeklyDigest:
    """Tests for generate_weekly_digest function."""

    @patch("src.state.db_helpers.get_unnotified_signals")
    @patch("src.state.db_helpers.mark_signal_notified")
    @patch("src.state.notify.format_state_digest")
    def test_returns_none_when_no_signals(self, mock_format, mock_mark, mock_get_signals):
        """Returns None when no signals are found."""
        mock_get_signals.return_value = []

        result = generate_weekly_digest()

        assert result is None
        mock_mark.assert_not_called()
        mock_format.assert_not_called()

    @patch("src.state.db_helpers.get_unnotified_signals")
    @patch("src.state.db_helpers.mark_signal_notified")
    @patch("src.state.notify.format_state_digest")
    def test_returns_formatted_digest(self, mock_format, mock_mark, mock_get_signals):
        """Returns formatted digest when signals exist."""
        mock_get_signals.side_effect = [
            # Medium severity signals
            [
                {
                    "signal_id": "sig-001",
                    "state": "TX",
                    "title": "Texas VA update",
                    "url": "https://example.com/tx",
                    "program": "PACT Act",
                }
            ],
            # Low severity signals
            [
                {
                    "signal_id": "sig-002",
                    "state": "CA",
                    "title": "California VA news",
                    "url": "https://example.com/ca",
                    "program": "General",
                }
            ],
        ]
        mock_format.return_value = {"text": "Weekly digest content"}

        result = generate_weekly_digest()

        assert result == {"text": "Weekly digest content"}
        # Should fetch medium then low severity
        assert mock_get_signals.call_count == 2
        mock_get_signals.assert_any_call(severity="medium")
        mock_get_signals.assert_any_call(severity="low")

    @patch("src.state.db_helpers.get_unnotified_signals")
    @patch("src.state.db_helpers.mark_signal_notified")
    @patch("src.state.notify.format_state_digest")
    def test_marks_signals_notified_when_not_dry_run(
        self, mock_format, mock_mark, mock_get_signals
    ):
        """Marks signals as notified when not in dry run mode."""
        mock_get_signals.side_effect = [
            [{"signal_id": "sig-001", "state": "TX", "title": "Test", "url": "https://test.com"}],
            [{"signal_id": "sig-002", "state": "CA", "title": "Test2", "url": "https://test2.com"}],
        ]
        mock_format.return_value = {"text": "Digest"}

        generate_weekly_digest(dry_run=False)

        assert mock_mark.call_count == 2
        mock_mark.assert_any_call("sig-001", "weekly_digest")
        mock_mark.assert_any_call("sig-002", "weekly_digest")

    @patch("src.state.db_helpers.get_unnotified_signals")
    @patch("src.state.db_helpers.mark_signal_notified")
    @patch("src.state.notify.format_state_digest")
    def test_does_not_mark_signals_in_dry_run(self, mock_format, mock_mark, mock_get_signals):
        """Does not mark signals as notified in dry run mode."""
        mock_get_signals.side_effect = [
            [{"signal_id": "sig-001", "state": "TX", "title": "Test", "url": "https://test.com"}],
            [],
        ]
        mock_format.return_value = {"text": "Digest"}

        generate_weekly_digest(dry_run=True)

        mock_mark.assert_not_called()

    @patch("src.state.db_helpers.get_unnotified_signals")
    @patch("src.state.db_helpers.mark_signal_notified")
    @patch("src.state.notify.format_state_digest")
    def test_groups_signals_by_state(self, mock_format, mock_mark, mock_get_signals):
        """Groups signals by state before formatting."""
        mock_get_signals.side_effect = [
            [
                {
                    "signal_id": "sig-001",
                    "state": "TX",
                    "title": "TX Signal",
                    "url": "https://tx.com",
                },
                {
                    "signal_id": "sig-002",
                    "state": "CA",
                    "title": "CA Signal",
                    "url": "https://ca.com",
                },
            ],
            [
                {
                    "signal_id": "sig-003",
                    "state": "TX",
                    "title": "TX Signal 2",
                    "url": "https://tx2.com",
                },
            ],
        ]
        mock_format.return_value = {"text": "Digest"}

        generate_weekly_digest()

        # Verify format_state_digest was called with grouped signals
        call_args = mock_format.call_args[0][0]
        assert "TX" in call_args
        assert "CA" in call_args
        assert len(call_args["TX"]) == 2
        assert len(call_args["CA"]) == 1


class TestSendDigestEmail:
    """Tests for _send_digest_email function."""

    @patch("src.notify_email.is_configured")
    def test_returns_false_when_not_configured(self, mock_configured):
        """Returns False when email is not configured."""
        mock_configured.return_value = False

        result = _send_digest_email("Test digest")

        assert result is False

    @patch("src.notify_email.is_configured")
    @patch("src.notify_email._send_email")
    @patch("src.notify_email._base_html_template")
    def test_sends_email_with_correct_subject(self, mock_template, mock_send, mock_configured):
        """Sends email with correct subject format."""
        mock_configured.return_value = True
        mock_template.return_value = "<html>Test</html>"
        mock_send.return_value = True

        result = _send_digest_email("Test digest content")

        assert result is True
        mock_send.assert_called_once()
        call_args = mock_send.call_args
        subject = call_args[0][0]
        assert "VA Signals" in subject
        assert "State Intelligence Weekly Digest" in subject

    @patch("src.notify_email.is_configured")
    @patch("src.notify_email._send_email")
    @patch("src.notify_email._base_html_template")
    def test_converts_markdown_formatting_to_html(self, mock_template, mock_send, mock_configured):
        """Converts Slack-style markdown to HTML."""
        mock_configured.return_value = True
        mock_template.return_value = "<html></html>"
        mock_send.return_value = True

        _send_digest_email("*bold text* and _italic text_")

        # Check the HTML content passed to template contains converted formatting
        call_args = mock_template.call_args
        content = call_args[0][1]
        assert "<strong>bold text</strong>" in content
        assert "<em>italic text</em>" in content

    @patch("src.notify_email.is_configured")
    @patch("src.notify_email._send_email")
    @patch("src.notify_email._base_html_template")
    def test_converts_slack_links_to_html(self, mock_template, mock_send, mock_configured):
        """Converts Slack-style links to HTML anchor tags."""
        mock_configured.return_value = True
        mock_template.return_value = "<html></html>"
        mock_send.return_value = True

        _send_digest_email("<https://example.com|Example Link>")

        call_args = mock_template.call_args
        content = call_args[0][1]
        assert 'href="https://example.com"' in content
        assert "Example Link" in content

    @patch("src.notify_email.is_configured")
    @patch("src.notify_email._send_email")
    @patch("src.notify_email._base_html_template")
    def test_includes_plain_text_fallback(self, mock_template, mock_send, mock_configured):
        """Includes plain text in email for fallback."""
        mock_configured.return_value = True
        mock_template.return_value = "<html></html>"
        mock_send.return_value = True

        _send_digest_email("Plain text content")

        call_args = mock_send.call_args
        plain_text = call_args[0][2]
        assert plain_text == "Plain text content"


class TestCLIArgumentParsing:
    """Tests for CLI argument parsing."""

    def test_parse_send_email_flag(self):
        """Parses --send-email flag correctly."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--send-email", action="store_true")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--verbose", "-v", action="store_true")

        args = parser.parse_args(["--send-email"])
        assert args.send_email is True
        assert args.dry_run is False

    def test_parse_dry_run_flag(self):
        """Parses --dry-run flag correctly."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--send-email", action="store_true")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--verbose", "-v", action="store_true")

        args = parser.parse_args(["--dry-run"])
        assert args.dry_run is True
        assert args.send_email is False

    def test_parse_verbose_flag(self):
        """Parses --verbose/-v flag correctly."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--send-email", action="store_true")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--verbose", "-v", action="store_true")

        args = parser.parse_args(["-v"])
        assert args.verbose is True

        args2 = parser.parse_args(["--verbose"])
        assert args2.verbose is True

    def test_parse_combined_flags(self):
        """Parses combined flags correctly."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--send-email", action="store_true")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--verbose", "-v", action="store_true")

        args = parser.parse_args(["--send-email", "--dry-run", "-v"])
        assert args.send_email is True
        assert args.dry_run is True
        assert args.verbose is True

    @patch("src.state.digest.generate_weekly_digest")
    @patch("src.state.digest._send_digest_email")
    @patch("sys.argv", ["digest", "--dry-run"])
    def test_main_with_dry_run(self, mock_send, mock_generate):
        """Main function respects dry run flag."""
        mock_generate.return_value = {"text": "Test digest"}

        # Call main (it will use sys.argv)
        with patch("builtins.print"):
            main()

        mock_generate.assert_called_once_with(dry_run=True)
        mock_send.assert_not_called()

    @patch("src.state.digest.generate_weekly_digest")
    @patch("src.state.digest._send_digest_email")
    @patch("sys.argv", ["digest", "--send-email"])
    def test_main_with_send_email(self, mock_send, mock_generate):
        """Main function sends email when flag is set."""
        mock_generate.return_value = {"text": "Test digest"}
        mock_send.return_value = True

        with patch("builtins.print"):
            main()

        mock_generate.assert_called_once_with(dry_run=False)
        mock_send.assert_called_once_with("Test digest")

    @patch("src.state.digest.generate_weekly_digest")
    @patch("sys.argv", ["digest"])
    def test_main_no_signals(self, mock_generate):
        """Main function handles no signals gracefully."""
        mock_generate.return_value = None

        with patch("builtins.print") as mock_print:
            main()

        mock_print.assert_any_call("No signals for weekly digest.")
