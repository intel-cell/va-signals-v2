"""Tests for email SMTP health check and /api/health email integration."""

import os
from unittest.mock import MagicMock, patch

from src.notify_email import check_smtp_health


class TestCheckSmtpHealth:
    """Tests for check_smtp_health function."""

    def test_returns_not_configured_when_env_missing(self):
        """Returns configured=False when env vars are not set."""
        with patch.dict(os.environ, {}, clear=True):
            result = check_smtp_health()
        assert result["configured"] is False
        assert result["reachable"] is False
        assert result["error"] is not None
        assert "not configured" in result["error"].lower()

    @patch("src.notify_email.smtplib.SMTP")
    def test_returns_reachable_on_success(self, mock_smtp_class):
        """Returns reachable=True when SMTP connection succeeds."""
        mock_smtp = MagicMock()
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

        with patch.dict(
            os.environ,
            {
                "SMTP_HOST": "smtp.example.com",
                "SMTP_PORT": "587",
                "SMTP_USER": "user@example.com",
                "SMTP_PASS": "password",
                "EMAIL_FROM": "from@example.com",
                "EMAIL_TO": "to@example.com",
            },
            clear=True,
        ):
            result = check_smtp_health()

        assert result["configured"] is True
        assert result["reachable"] is True
        assert result["error"] is None
        mock_smtp.starttls.assert_called_once()
        mock_smtp.login.assert_called_once_with("user@example.com", "password")
        mock_smtp.noop.assert_called_once()

    @patch("src.notify_email.smtplib.SMTP")
    def test_returns_unreachable_on_smtp_error(self, mock_smtp_class):
        """Returns reachable=False with error message on SMTP failure."""
        mock_smtp_class.side_effect = Exception("Connection refused")

        with patch.dict(
            os.environ,
            {
                "SMTP_HOST": "smtp.example.com",
                "SMTP_PORT": "587",
                "SMTP_USER": "user@example.com",
                "SMTP_PASS": "password",
                "EMAIL_FROM": "from@example.com",
                "EMAIL_TO": "to@example.com",
            },
            clear=True,
        ):
            result = check_smtp_health()

        assert result["configured"] is True
        assert result["reachable"] is False
        assert "Connection refused" in result["error"]

    @patch("src.notify_email.smtplib.SMTP")
    def test_returns_unreachable_on_auth_error(self, mock_smtp_class):
        """Returns reachable=False when login fails."""
        mock_smtp = MagicMock()
        mock_smtp.login.side_effect = Exception("Authentication failed")
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

        with patch.dict(
            os.environ,
            {
                "SMTP_HOST": "smtp.example.com",
                "SMTP_PORT": "587",
                "SMTP_USER": "user@example.com",
                "SMTP_PASS": "wrongpass",
                "EMAIL_FROM": "from@example.com",
                "EMAIL_TO": "to@example.com",
            },
            clear=True,
        ):
            result = check_smtp_health()

        assert result["configured"] is True
        assert result["reachable"] is False
        assert "Authentication failed" in result["error"]
