"""Integration tests for email notification system."""

import os
from unittest.mock import patch, MagicMock

import pytest

from src.notify_email import (
    is_configured,
    _get_config,
    _send_email,
    send_error_alert,
    send_new_docs_alert,
    send_daily_digest,
    _base_html_template,
    _format_timestamp,
)


class TestEmailConfiguration:
    """Tests for email configuration detection."""

    def test_is_configured_returns_true_when_all_vars_set(self):
        """Returns True when all required env vars are set."""
        with patch.dict(os.environ, {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "587",
            "SMTP_USER": "user@example.com",
            "SMTP_PASS": "password123",
            "EMAIL_FROM": "from@example.com",
            "EMAIL_TO": "to@example.com",
        }, clear=True):
            assert is_configured() is True

    def test_is_configured_returns_false_when_missing_host(self):
        """Returns False when SMTP_HOST is missing."""
        with patch.dict(os.environ, {
            "SMTP_PORT": "587",
            "SMTP_USER": "user@example.com",
            "SMTP_PASS": "password123",
            "EMAIL_FROM": "from@example.com",
            "EMAIL_TO": "to@example.com",
        }, clear=True):
            assert is_configured() is False

    def test_is_configured_returns_false_when_missing_user(self):
        """Returns False when SMTP_USER is missing."""
        with patch.dict(os.environ, {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "587",
            "SMTP_PASS": "password123",
            "EMAIL_FROM": "from@example.com",
            "EMAIL_TO": "to@example.com",
        }, clear=True):
            assert is_configured() is False

    def test_is_configured_returns_false_when_missing_password(self):
        """Returns False when SMTP_PASS is missing."""
        with patch.dict(os.environ, {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "587",
            "SMTP_USER": "user@example.com",
            "EMAIL_FROM": "from@example.com",
            "EMAIL_TO": "to@example.com",
        }, clear=True):
            assert is_configured() is False

    def test_is_configured_returns_false_when_missing_from(self):
        """Returns False when EMAIL_FROM is missing."""
        with patch.dict(os.environ, {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "587",
            "SMTP_USER": "user@example.com",
            "SMTP_PASS": "password123",
            "EMAIL_TO": "to@example.com",
        }, clear=True):
            assert is_configured() is False

    def test_is_configured_returns_false_when_missing_to(self):
        """Returns False when EMAIL_TO is missing."""
        with patch.dict(os.environ, {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "587",
            "SMTP_USER": "user@example.com",
            "SMTP_PASS": "password123",
            "EMAIL_FROM": "from@example.com",
        }, clear=True):
            assert is_configured() is False

    def test_get_config_returns_defaults(self):
        """Returns empty strings when env vars not set."""
        with patch.dict(os.environ, {}, clear=True):
            config = _get_config()
            assert config["host"] == ""
            assert config["port"] == 587  # Default port
            assert config["user"] == ""

    def test_get_config_reads_env_vars(self):
        """Reads configuration from environment variables."""
        with patch.dict(os.environ, {
            "SMTP_HOST": "mail.example.com",
            "SMTP_PORT": "465",
            "SMTP_USER": "test@example.com",
            "SMTP_PASS": "secret",
            "EMAIL_FROM": "noreply@example.com",
            "EMAIL_TO": "alerts@example.com",
        }, clear=True):
            config = _get_config()
            assert config["host"] == "mail.example.com"
            assert config["port"] == 465
            assert config["user"] == "test@example.com"
            assert config["password"] == "secret"
            assert config["from_addr"] == "noreply@example.com"
            assert config["to_addr"] == "alerts@example.com"


class TestSendEmail:
    """Tests for _send_email function."""

    def test_send_email_returns_false_when_not_configured(self):
        """Returns False when email is not configured."""
        with patch.dict(os.environ, {}, clear=True):
            result = _send_email("Subject", "<html></html>", "Plain text")
            assert result is False

    @patch("src.notify_email.smtplib.SMTP")
    def test_send_email_sends_via_smtp(self, mock_smtp_class):
        """Sends email via SMTP when configured."""
        mock_smtp = MagicMock()
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

        with patch.dict(os.environ, {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "587",
            "SMTP_USER": "user@example.com",
            "SMTP_PASS": "password",
            "EMAIL_FROM": "from@example.com",
            "EMAIL_TO": "to@example.com",
        }, clear=True):
            result = _send_email("Test Subject", "<html>Body</html>", "Body")

        assert result is True
        mock_smtp.starttls.assert_called_once()
        mock_smtp.login.assert_called_once_with("user@example.com", "password")
        mock_smtp.sendmail.assert_called_once()

    @patch("src.notify_email.smtplib.SMTP")
    def test_send_email_handles_multiple_recipients(self, mock_smtp_class):
        """Handles comma-separated recipients correctly."""
        mock_smtp = MagicMock()
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

        with patch.dict(os.environ, {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "587",
            "SMTP_USER": "user@example.com",
            "SMTP_PASS": "password",
            "EMAIL_FROM": "from@example.com",
            "EMAIL_TO": "to1@example.com, to2@example.com",
        }, clear=True):
            _send_email("Subject", "<html></html>", "Text")

        # Verify sendmail called with list of recipients
        call_args = mock_smtp.sendmail.call_args
        recipients = call_args[0][1]
        assert "to1@example.com" in recipients
        assert "to2@example.com" in recipients

    @patch("src.notify_email.smtplib.SMTP")
    def test_send_email_returns_false_on_error(self, mock_smtp_class):
        """Returns False on SMTP error without raising."""
        mock_smtp_class.side_effect = Exception("SMTP connection failed")

        with patch.dict(os.environ, {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "587",
            "SMTP_USER": "user@example.com",
            "SMTP_PASS": "password",
            "EMAIL_FROM": "from@example.com",
            "EMAIL_TO": "to@example.com",
        }, clear=True):
            result = _send_email("Subject", "<html></html>", "Text")

        # Should return False, not raise
        assert result is False


class TestSendErrorAlert:
    """Tests for send_error_alert function."""

    @patch("src.notify_email._send_email")
    def test_send_error_alert_constructs_message(self, mock_send):
        """Constructs error alert with correct information."""
        mock_send.return_value = True

        with patch.dict(os.environ, {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "587",
            "SMTP_USER": "user@example.com",
            "SMTP_PASS": "password",
            "EMAIL_FROM": "from@example.com",
            "EMAIL_TO": "to@example.com",
        }, clear=True):
            result = send_error_alert(
                source_id="govinfo_fr_bulk",
                errors=["API timeout", "Database connection failed"],
                run_record={
                    "started_at": "2026-01-20T10:00:00Z",
                    "ended_at": "2026-01-20T10:05:00Z",
                    "status": "ERROR",
                    "records_fetched": 0,
                }
            )

        assert result is True
        mock_send.assert_called_once()

        # Check subject
        call_args = mock_send.call_args
        subject = call_args[0][0]
        assert "ERROR" in subject
        assert "govinfo_fr_bulk" in subject

        # Check HTML contains error details
        html = call_args[0][1]
        assert "API timeout" in html
        assert "Database connection failed" in html

        # Check plain text fallback
        plain_text = call_args[0][2]
        assert "ERROR" in plain_text
        assert "govinfo_fr_bulk" in plain_text

    def test_send_error_alert_returns_false_when_not_configured(self):
        """Returns False when email not configured."""
        with patch.dict(os.environ, {}, clear=True):
            result = send_error_alert(
                source_id="test",
                errors=["Error"],
                run_record={"started_at": "", "ended_at": "", "status": "ERROR"}
            )
        assert result is False


class TestSendNewDocsAlert:
    """Tests for send_new_docs_alert function."""

    @patch("src.notify_email._send_email")
    def test_send_new_docs_alert_constructs_message(self, mock_send):
        """Constructs new docs alert with correct information."""
        mock_send.return_value = True

        with patch.dict(os.environ, {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "587",
            "SMTP_USER": "user@example.com",
            "SMTP_PASS": "password",
            "EMAIL_FROM": "from@example.com",
            "EMAIL_TO": "to@example.com",
        }, clear=True):
            result = send_new_docs_alert(
                source_id="govinfo_fr_bulk",
                docs=[
                    {
                        "doc_id": "FR-2026-01234",
                        "first_seen_at": "2026-01-20T10:00:00Z",
                        "source_url": "https://federalregister.gov/doc/2026-01234",
                    },
                    {
                        "doc_id": "FR-2026-01235",
                        "first_seen_at": "2026-01-20T10:01:00Z",
                        "source_url": "https://federalregister.gov/doc/2026-01235",
                    },
                ],
                run_record={
                    "started_at": "2026-01-20T10:00:00Z",
                    "records_fetched": 100,
                }
            )

        assert result is True
        mock_send.assert_called_once()

        # Check subject
        call_args = mock_send.call_args
        subject = call_args[0][0]
        assert "2 New Documents" in subject

        # Check HTML contains document IDs
        html = call_args[0][1]
        assert "FR-2026-01234" in html
        assert "FR-2026-01235" in html

    @patch("src.notify_email._send_email")
    def test_send_new_docs_alert_singular_subject(self, mock_send):
        """Uses singular form in subject for one document."""
        mock_send.return_value = True

        with patch.dict(os.environ, {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "587",
            "SMTP_USER": "user@example.com",
            "SMTP_PASS": "password",
            "EMAIL_FROM": "from@example.com",
            "EMAIL_TO": "to@example.com",
        }, clear=True):
            send_new_docs_alert(
                source_id="test",
                docs=[{"doc_id": "DOC-001", "source_url": ""}],
                run_record={"started_at": "", "records_fetched": 1}
            )

        call_args = mock_send.call_args
        subject = call_args[0][0]
        assert "1 New Document Found" in subject

    @patch("src.notify_email._send_email")
    def test_send_new_docs_alert_limits_display(self, mock_send):
        """Limits displayed documents to 10 with '+X more' indicator."""
        mock_send.return_value = True

        docs = [
            {"doc_id": f"DOC-{i:03d}", "source_url": f"https://example.com/{i}"}
            for i in range(15)
        ]

        with patch.dict(os.environ, {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "587",
            "SMTP_USER": "user@example.com",
            "SMTP_PASS": "password",
            "EMAIL_FROM": "from@example.com",
            "EMAIL_TO": "to@example.com",
        }, clear=True):
            send_new_docs_alert(
                source_id="test",
                docs=docs,
                run_record={"started_at": "", "records_fetched": 15}
            )

        call_args = mock_send.call_args
        html = call_args[0][1]
        plain = call_args[0][2]

        # Should show "+ 5 more"
        assert "+ 5 more" in html or "+5 more" in html or "5 more" in html
        assert "5 more" in plain

    def test_send_new_docs_alert_returns_false_when_not_configured(self):
        """Returns False when email not configured."""
        with patch.dict(os.environ, {}, clear=True):
            result = send_new_docs_alert(
                source_id="test",
                docs=[{"doc_id": "DOC", "source_url": ""}],
                run_record={}
            )
        assert result is False


class TestSendDailyDigest:
    """Tests for send_daily_digest function."""

    @patch("src.notify_email._send_email")
    def test_send_daily_digest_constructs_message(self, mock_send):
        """Constructs daily digest with run summary."""
        mock_send.return_value = True

        with patch.dict(os.environ, {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "587",
            "SMTP_USER": "user@example.com",
            "SMTP_PASS": "password",
            "EMAIL_FROM": "from@example.com",
            "EMAIL_TO": "to@example.com",
        }, clear=True):
            result = send_daily_digest(
                runs=[
                    {"source_id": "source_a", "status": "SUCCESS", "records_fetched": 50},
                    {"source_id": "source_b", "status": "NO_DATA", "records_fetched": 0},
                    {"source_id": "source_c", "status": "ERROR", "records_fetched": 10},
                ],
                new_docs_by_source={
                    "source_a": [{"doc_id": "DOC-1"}, {"doc_id": "DOC-2"}],
                    "source_b": [],
                    "source_c": [],
                },
                date_label="2026-01-20"
            )

        assert result is True
        mock_send.assert_called_once()

        call_args = mock_send.call_args
        subject = call_args[0][0]
        html = call_args[0][1]

        assert "Daily Digest" in subject
        assert "2026-01-20" in subject
        assert "source_a" in html
        assert "SUCCESS" in html

    def test_send_daily_digest_returns_false_for_empty_runs(self):
        """Returns False when no runs to report."""
        result = send_daily_digest(runs=[], new_docs_by_source={})
        assert result is False


class TestHTMLTemplate:
    """Tests for HTML template generation."""

    def test_base_html_template_includes_title(self):
        """Includes title in template."""
        html = _base_html_template("Test Title", "<p>Content</p>")
        assert "Test Title" in html

    def test_base_html_template_includes_content(self):
        """Includes content in template."""
        html = _base_html_template("Title", "<p>My Content</p>")
        assert "My Content" in html

    def test_base_html_template_includes_va_branding(self):
        """Includes VA Signals branding."""
        html = _base_html_template("Title", "Content")
        assert "VA Signals" in html

    def test_base_html_template_includes_footer(self):
        """Includes footer in template."""
        html = _base_html_template("Title", "Content", footer="Custom Footer")
        assert "Custom Footer" in html


class TestFormatTimestamp:
    """Tests for timestamp formatting."""

    def test_format_timestamp_utc_z_suffix(self):
        """Formats timestamp with Z suffix correctly."""
        result = _format_timestamp("2026-01-20T10:30:00Z")
        assert "2026-01-20" in result
        assert "10:30:00" in result
        assert "UTC" in result

    def test_format_timestamp_utc_offset(self):
        """Formats timestamp with +00:00 offset correctly."""
        result = _format_timestamp("2026-01-20T10:30:00+00:00")
        assert "2026-01-20" in result
        assert "10:30:00" in result

    def test_format_timestamp_invalid_returns_original(self):
        """Returns original string for invalid format."""
        result = _format_timestamp("not-a-timestamp")
        assert result == "not-a-timestamp"

    def test_format_timestamp_empty_returns_empty(self):
        """Returns empty string for empty input."""
        result = _format_timestamp("")
        assert result == ""
