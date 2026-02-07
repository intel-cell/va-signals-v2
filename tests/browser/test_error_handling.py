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
        """Zero JavaScript console errors on initial dashboard load."""
        errors = collect_console_errors(authenticated_page)
        wait_for_dashboard_load(authenticated_page)
        authenticated_page.wait_for_timeout(1000)
        assert len(errors) == 0, f"Console errors on dashboard load: {errors}"

    def test_no_console_errors_all_tabs(self, authenticated_page):
        """Zero JavaScript console errors when visiting all 6 tabs."""
        errors = collect_console_errors(authenticated_page)
        wait_for_dashboard_load(authenticated_page)
        for tab in TAB_NAMES:
            switch_to_tab(authenticated_page, tab)
            authenticated_page.wait_for_timeout(500)
        assert len(errors) == 0, f"Console errors across tabs: {errors}"

    def test_404_page_handling(self, authenticated_page):
        """Navigating to a non-existent URL returns a meaningful response (not a crash)."""
        response = authenticated_page.goto(f"{BASE_URL}/nonexistent")
        # Server should return a response (not crash/hang)
        assert response is not None, "No response from server for /nonexistent"
        status = response.status
        # Accept 404 or redirect (302 to login) -- either is graceful handling
        assert status in (404, 302, 200), f"Unexpected status {status} for /nonexistent"

    def test_invalid_api_endpoint(self, authenticated_page):
        """Navigating to an invalid API endpoint returns a structured response (not 500)."""
        response = authenticated_page.goto(f"{BASE_URL}/api/nonexistent")
        assert response is not None, "No response from server for /api/nonexistent"
        status = response.status
        # Should be 404 or 405, not 500 (internal server error)
        assert status != 500, "Server returned 500 for invalid API endpoint"

    def test_login_page_no_console_errors(self, page):
        """Login page loads without JavaScript console errors."""
        errors = collect_console_errors(page)
        page.goto(f"{BASE_URL}/login.html", wait_until="domcontentloaded")
        page.wait_for_timeout(1000)
        assert len(errors) == 0, f"Console errors on login page: {errors}"
