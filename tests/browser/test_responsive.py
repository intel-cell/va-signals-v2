"""Tests for responsive design across viewport sizes."""

import pytest

from tests.browser.test_utils import (
    SELECTORS,
    TAB_NAMES,
    switch_to_tab,
    wait_for_dashboard_load,
)

pytestmark = pytest.mark.playwright


class TestResponsive:
    """Verify dashboard renders correctly across different viewports."""

    def test_desktop_tabs_visible(self, authenticated_page):
        """All 6 tab buttons are visible on desktop viewport (1920x1080)."""
        wait_for_dashboard_load(authenticated_page)
        tabs = authenticated_page.locator(".tab-btn").all()
        assert len(tabs) == 6, f"Expected 6 tab buttons, got {len(tabs)}"
        visible_count = sum(1 for t in tabs if t.is_visible())
        assert visible_count == 6, f"Expected all 6 tabs visible, got {visible_count}"

    def test_desktop_classification_banner(self, authenticated_page):
        """Classification banner renders on desktop."""
        wait_for_dashboard_load(authenticated_page)
        banner = authenticated_page.locator(SELECTORS["common"]["classification_banner"])
        assert banner.is_visible()
        assert "UNCLASSIFIED" in banner.text_content()

    def test_desktop_header_elements(self, authenticated_page):
        """Header elements render on desktop."""
        wait_for_dashboard_load(authenticated_page)
        header = authenticated_page.locator("header")
        assert header.count() >= 1, "Header element not found"
        title = authenticated_page.locator(SELECTORS["header"]["title"])
        assert title.count() >= 1, "Header h1 title not found"

    def test_dashboard_container_present(self, authenticated_page):
        """Dashboard container renders correctly."""
        wait_for_dashboard_load(authenticated_page)
        tabs = authenticated_page.locator(".tab-btn").all()
        assert len(tabs) == 6, f"Expected 6 tabs, got {len(tabs)}"
        dashboard = authenticated_page.locator(SELECTORS["common"]["dashboard"])
        assert dashboard.is_visible()

    def test_tab_switching_works(self, authenticated_page):
        """Can switch between tabs and see panel content."""
        wait_for_dashboard_load(authenticated_page)
        for tab_name in TAB_NAMES:
            switch_to_tab(authenticated_page, tab_name)
            authenticated_page.wait_for_timeout(300)
            panel = authenticated_page.locator(SELECTORS["panels"][tab_name])
            assert panel.count() == 1, f"Panel for tab '{tab_name}' not found"

    def test_classification_banner_persists(self, authenticated_page):
        """Classification banner stays visible across tab switches."""
        wait_for_dashboard_load(authenticated_page)
        for tab_name in ["command", "federal", "oversight"]:
            switch_to_tab(authenticated_page, tab_name)
            banner = authenticated_page.locator(SELECTORS["common"]["classification_banner"])
            assert banner.is_visible(), f"Banner should be visible on {tab_name} tab"
