"""Playwright tests for authentication flow and RBAC visibility.

Validates session cookie auth bypass, redirect behavior,
role-based UI elements, and multi-role dashboard access.
"""

import pytest

from tests.browser.test_utils import BASE_URL, SELECTORS, wait_for_dashboard_load

pytestmark = pytest.mark.playwright


class TestAuthFlow:
    """Authentication flow and role-based access tests."""

    def test_unauthenticated_redirects_to_login(self, page):
        """Accessing / without auth redirects to login page."""
        page.goto(f"{BASE_URL}/", wait_until="domcontentloaded")
        page.wait_for_timeout(1000)  # Allow redirect
        assert "login" in page.url.lower()

    def test_authenticated_sees_dashboard(self, authenticated_page):
        """Commander session cookie grants dashboard access with 6 tabs."""
        wait_for_dashboard_load(authenticated_page)
        tabs = authenticated_page.locator(".tab-btn").all()
        assert len(tabs) == 6, f"Expected 6 tabs, got {len(tabs)}"

    def test_user_menu_shows_commander_role(self, authenticated_page):
        """User dropdown shows 'commander' role for commander session."""
        wait_for_dashboard_load(authenticated_page)
        authenticated_page.click(SELECTORS["header"]["user_menu_btn"])
        authenticated_page.wait_for_timeout(300)  # dropdown animation
        role = authenticated_page.locator(SELECTORS["header"]["user_role"])
        assert role.is_visible()
        assert "commander" in role.text_content().lower()

    def test_user_menu_shows_email(self, authenticated_page):
        """User dropdown shows commander@test.dev email."""
        wait_for_dashboard_load(authenticated_page)
        authenticated_page.click(SELECTORS["header"]["user_menu_btn"])
        authenticated_page.wait_for_timeout(300)
        email = authenticated_page.locator(SELECTORS["header"]["user_email"])
        assert email.is_visible()
        assert "commander@test.dev" in email.text_content()

    def test_logout_button_visible(self, authenticated_page):
        """Logout button is visible in user dropdown."""
        wait_for_dashboard_load(authenticated_page)
        authenticated_page.click(SELECTORS["header"]["user_menu_btn"])
        authenticated_page.wait_for_timeout(300)
        logout = authenticated_page.locator(SELECTORS["header"]["logout_btn"])
        assert logout.is_visible()

    def test_audit_log_visible_for_commander(self, authenticated_page):
        """Audit log button is visible for commander role."""
        wait_for_dashboard_load(authenticated_page)
        authenticated_page.click(SELECTORS["header"]["user_menu_btn"])
        authenticated_page.wait_for_timeout(300)
        audit = authenticated_page.locator(SELECTORS["header"]["audit_log_btn"])
        # audit-log-btn starts hidden (style="display: none;") and JS
        # should reveal it for commander role after auth context loads
        assert audit.is_visible()

    def test_analyst_sees_dashboard(self, analyst_page):
        """Analyst session cookie grants dashboard access with 6 tabs."""
        wait_for_dashboard_load(analyst_page)
        tabs = analyst_page.locator(".tab-btn").all()
        assert len(tabs) == 6, f"Expected 6 tabs, got {len(tabs)}"

    def test_viewer_sees_dashboard(self, viewer_page):
        """Viewer session cookie grants dashboard access with 6 tabs."""
        wait_for_dashboard_load(viewer_page)
        tabs = viewer_page.locator(".tab-btn").all()
        assert len(tabs) == 6, f"Expected 6 tabs, got {len(tabs)}"
