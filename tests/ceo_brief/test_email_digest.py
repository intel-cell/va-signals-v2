"""Tests for CEO Brief email digest notification."""

from unittest.mock import patch

from src.notify_email import send_ceo_brief_digest


def _make_result(success=True, brief_id="brief-2026-02-07"):
    """Build a sample result dict."""
    return {
        "success": success,
        "brief_id": brief_id,
        "stats": {
            "period_start": "2026-01-31",
            "period_end": "2026-02-07",
            "total_deltas": 42,
            "top_issues": 5,
            "enhanced": True,
            "sources": {
                "federal_register": 10,
                "bills": 8,
                "hearings": 5,
                "oversight": 12,
                "state": 7,
            },
        },
        "error": None,
    }


class TestCeoBriefDigest:
    @patch("src.notify_email._send_email", return_value=True)
    def test_sends_on_success(self, mock_send):
        result = _make_result()
        assert send_ceo_brief_digest(result) is True
        mock_send.assert_called_once()
        subject = mock_send.call_args[0][0]
        assert "SUCCESS" in subject

    @patch("src.notify_email._send_email", return_value=True)
    def test_sends_on_failure(self, mock_send):
        result = _make_result(success=False)
        result["error"] = "Pipeline crashed"
        assert send_ceo_brief_digest(result) is True
        subject = mock_send.call_args[0][0]
        assert "FAILED" in subject

    @patch("src.notify_email._send_email", return_value=True)
    def test_html_contains_brief_id(self, mock_send):
        result = _make_result()
        send_ceo_brief_digest(result)
        html = mock_send.call_args[0][1]
        assert "brief-2026-02-07" in html

    @patch("src.notify_email._send_email", return_value=True)
    def test_html_contains_period(self, mock_send):
        result = _make_result()
        send_ceo_brief_digest(result)
        html = mock_send.call_args[0][1]
        assert "2026-01-31" in html
        assert "2026-02-07" in html

    @patch("src.notify_email._send_email", return_value=True)
    def test_html_contains_source_counts(self, mock_send):
        result = _make_result()
        send_ceo_brief_digest(result)
        html = mock_send.call_args[0][1]
        assert "10" in html  # FR count
        assert "42" in html  # total deltas

    @patch("src.notify_email._send_email", return_value=True)
    def test_plain_text_fallback(self, mock_send):
        result = _make_result()
        send_ceo_brief_digest(result)
        text = mock_send.call_args[0][2]
        assert "CEO Brief" in text
        assert "42" in text  # total deltas

    @patch("src.notify_email._send_email", return_value=False)
    def test_returns_false_on_send_failure(self, mock_send):
        result = _make_result()
        assert send_ceo_brief_digest(result) is False

    @patch("src.notify_email._send_email", return_value=True)
    def test_handles_missing_stats_gracefully(self, mock_send):
        result = {"success": True, "brief_id": "test", "stats": {}}
        # Should not raise
        send_ceo_brief_digest(result)
        mock_send.assert_called_once()
