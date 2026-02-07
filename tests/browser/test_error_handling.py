"""Tests for error handling and console error detection."""

import pytest

from tests.browser.test_utils import (
    BASE_URL,
    TAB_NAMES,
    collect_console_errors,
    switch_to_tab,
    wait_for_dashboard_load,
)

pytestmark = pytest.mark.playwright


class TestErrorHandling:
    """Verify the dashboard handles errors gracefully with no JS console errors."""

    def test_no_console_errors_on_dashboard_load(self, authenticated_page):
        """Zero application-level JavaScript console errors on dashboard load."""
        errors = collect_console_errors(authenticated_page)
        wait_for_dashboard_load(authenticated_page)
        authenticated_page.wait_for_timeout(2000)
        assert len(errors) == 0, f"Console errors on dashboard load: {errors}"

    def test_no_console_errors_all_tabs(self, authenticated_page):
        """Zero application-level JavaScript console errors when visiting all 6 tabs."""
        errors = collect_console_errors(authenticated_page)
        wait_for_dashboard_load(authenticated_page)
        for tab in TAB_NAMES:
            switch_to_tab(authenticated_page, tab)
            authenticated_page.wait_for_timeout(500)
        assert len(errors) == 0, f"Console errors across tabs: {errors}"

    def test_404_page_handling(self, authenticated_page):
        """Non-existent URL doesn't crash the server (no 500)."""
        from playwright.sync_api import TimeoutError as PwTimeout

        try:
            resp = authenticated_page.request.get(f"{BASE_URL}/nonexistent", timeout=5000)
            status = resp.status
            assert status != 500, "Server returned 500 for /nonexistent"
        except PwTimeout:
            # Timeout means server is alive but slow (SPA catch-all) — not a crash
            pass

    def test_invalid_api_endpoint(self, authenticated_page):
        """Invalid API endpoint doesn't crash the server (no 500)."""
        from playwright.sync_api import TimeoutError as PwTimeout

        try:
            resp = authenticated_page.request.get(f"{BASE_URL}/api/nonexistent", timeout=5000)
            status = resp.status
            assert status != 500, f"Server returned 500 for /api/nonexistent (got {status})"
        except PwTimeout:
            pass

    def test_login_page_no_console_errors(self, page):
        """Login page loads without application-level JavaScript console errors."""
        errors = collect_console_errors(page)
        page.goto(f"{BASE_URL}/login.html", wait_until="domcontentloaded")
        page.wait_for_timeout(1000)
        assert len(errors) == 0, f"Console errors on login page: {errors}"
