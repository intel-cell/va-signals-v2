"""Smoke test: verify infrastructure works before full test authoring."""

import pytest

from tests.browser.test_utils import BASE_URL, SELECTORS, wait_for_dashboard_load

pytestmark = pytest.mark.playwright


class TestSmoke:
    """Validate server connectivity and auth bypass."""

    def test_login_page_loads(self, page):
        """Server serves the login page on unauthenticated access."""
        page.goto(f"{BASE_URL}/login.html", wait_until="domcontentloaded")
        assert "Command Post Login" in page.title()

    def test_login_form_present(self, page):
        """Login page has email and password fields."""
        page.goto(f"{BASE_URL}/login.html", wait_until="domcontentloaded")
        assert page.locator(SELECTORS["login"]["email"]).is_visible()
        assert page.locator(SELECTORS["login"]["password"]).is_visible()
        assert page.locator(SELECTORS["login"]["submit"]).is_visible()

    def test_auth_bypass_cookie_works(self, authenticated_page):
        """Session cookie injection grants dashboard access."""
        wait_for_dashboard_load(authenticated_page)
        tabs = authenticated_page.locator(".tab-btn").all()
        assert len(tabs) == 6, f"Expected 6 tabs, got {len(tabs)}"

    def test_classification_banner_visible(self, authenticated_page):
        """Classification banner renders on dashboard."""
        wait_for_dashboard_load(authenticated_page)
        banner = authenticated_page.locator(SELECTORS["common"]["classification_banner"])
        assert banner.is_visible()
        assert "UNCLASSIFIED" in banner.text_content()
