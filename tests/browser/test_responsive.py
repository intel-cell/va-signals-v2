"""Tests for responsive design across viewport sizes."""

import pytest

from tests.browser.conftest import _make_session_cookie
from tests.browser.test_utils import (
    BASE_URL,
    SELECTORS,
    TAB_NAMES,
    switch_to_tab,
    wait_for_dashboard_load,
)

pytestmark = pytest.mark.playwright


class TestResponsive:
    """Verify dashboard renders correctly across mobile, tablet, and wide viewports."""

    def test_mobile_tabs_visible(self, mobile_page):
        """Tab buttons are still visible/accessible on mobile viewport (390x844)."""
        wait_for_dashboard_load(mobile_page)
        tabs = mobile_page.locator(".tab-btn").all()
        assert len(tabs) == 6, f"Expected 6 tab buttons on mobile, got {len(tabs)}"
        # At least some tabs should be visible (may require scrolling)
        visible_count = sum(1 for t in tabs if t.is_visible())
        assert visible_count > 0, "No tab buttons visible on mobile viewport"

    def test_mobile_classification_banner(self, mobile_page):
        """Classification banner still renders on mobile."""
        wait_for_dashboard_load(mobile_page)
        banner = mobile_page.locator(SELECTORS["common"]["classification_banner"])
        assert banner.is_visible()
        assert "UNCLASSIFIED" in banner.text_content()

    def test_mobile_header_elements(self, mobile_page):
        """Header elements render on mobile (may be collapsed/hamburger)."""
        wait_for_dashboard_load(mobile_page)
        header = mobile_page.locator("header.header")
        assert header.is_visible()
        # Title should be present in the DOM
        title = mobile_page.locator(SELECTORS["header"]["title"])
        assert title.count() == 1, "Header h1 title not found on mobile"

    def test_tablet_viewport(self, browser):
        """Dashboard loads with all 6 tabs on tablet viewport (768x1024)."""
        context = browser.new_context(viewport={"width": 768, "height": 1024})
        context.add_cookies(_make_session_cookie("test-commander-uid", "commander@test.dev"))
        page = context.new_page()
        try:
            page.goto(f"{BASE_URL}/")
            page.wait_for_load_state("networkidle")
            page.wait_for_selector(".tab-btn", timeout=10000)
            tabs = page.locator(".tab-btn").all()
            assert len(tabs) == 6, f"Expected 6 tabs on tablet, got {len(tabs)}"
            # Classification banner should still be present
            banner = page.locator(SELECTORS["common"]["classification_banner"])
            assert banner.is_visible()
        finally:
            page.close()
            context.close()

    def test_wide_viewport(self, browser):
        """Dashboard loads without layout issues on wide viewport (2560x1440)."""
        context = browser.new_context(viewport={"width": 2560, "height": 1440})
        context.add_cookies(_make_session_cookie("test-commander-uid", "commander@test.dev"))
        page = context.new_page()
        try:
            page.goto(f"{BASE_URL}/")
            page.wait_for_load_state("networkidle")
            page.wait_for_selector(".tab-btn", timeout=10000)
            tabs = page.locator(".tab-btn").all()
            assert len(tabs) == 6, f"Expected 6 tabs on wide viewport, got {len(tabs)}"
            # Dashboard container should be present
            dashboard = page.locator(SELECTORS["common"]["dashboard"])
            assert dashboard.is_visible()
        finally:
            page.close()
            context.close()

    def test_mobile_tab_switching(self, mobile_page):
        """Can switch between tabs on mobile and see panel content."""
        wait_for_dashboard_load(mobile_page)
        for tab_name in TAB_NAMES:
            switch_to_tab(mobile_page, tab_name)
            mobile_page.wait_for_timeout(300)
            panel = mobile_page.locator(SELECTORS["panels"][tab_name])
            assert panel.count() == 1, f"Panel for tab '{tab_name}' not found on mobile"
