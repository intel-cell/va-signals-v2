"""Tests for main dashboard tab navigation mechanics."""

import pytest

from tests.browser.test_utils import (
    SELECTORS,
    TAB_NAMES,
    switch_to_tab,
    wait_for_dashboard_load,
)

pytestmark = pytest.mark.playwright


class TestTabNavigation:
    """Verify tab switching, active states, and panel visibility."""

    def test_six_tabs_present(self, authenticated_page):
        """Dashboard renders exactly 6 tab buttons."""
        wait_for_dashboard_load(authenticated_page)
        tabs = authenticated_page.locator(".tab-btn").all()
        assert len(tabs) == 6, f"Expected 6 tabs, got {len(tabs)}"

    def test_default_active_tab(self, authenticated_page):
        """On load, the 'command' tab has the active class."""
        wait_for_dashboard_load(authenticated_page)
        command_tab = authenticated_page.locator(SELECTORS["tabs"]["command"])
        classes = command_tab.get_attribute("class")
        assert "active" in classes, f"Command tab should be active on load, got classes: {classes}"

    def test_command_panel_visible_by_default(self, authenticated_page):
        """Command panel is visible on load; all other panels are hidden."""
        wait_for_dashboard_load(authenticated_page)
        assert authenticated_page.locator(SELECTORS["panels"]["command"]).is_visible()
        for tab_name in TAB_NAMES:
            if tab_name == "command":
                continue
            panel = authenticated_page.locator(SELECTORS["panels"][tab_name])
            assert not panel.is_visible(), f"{tab_name} panel should be hidden on load"

    def test_switch_to_each_tab(self, authenticated_page):
        """Clicking each tab button makes its panel visible."""
        wait_for_dashboard_load(authenticated_page)
        for tab_name in TAB_NAMES:
            switch_to_tab(authenticated_page, tab_name)
            panel = authenticated_page.locator(SELECTORS["panels"][tab_name])
            assert panel.is_visible(), f"{tab_name} panel should be visible after clicking its tab"

    def test_tab_active_class_follows_click(self, authenticated_page):
        """Clicking 'federal' tab moves the active class from 'command' to 'federal'."""
        wait_for_dashboard_load(authenticated_page)
        switch_to_tab(authenticated_page, "federal")

        federal_tab = authenticated_page.locator(SELECTORS["tabs"]["federal"])
        command_tab = authenticated_page.locator(SELECTORS["tabs"]["command"])

        federal_classes = federal_tab.get_attribute("class")
        command_classes = command_tab.get_attribute("class")

        assert "active" in federal_classes, "Federal tab should have active class after click"
        assert "active" not in command_classes, "Command tab should lose active class"

    def test_header_elements_persist_across_tabs(self, authenticated_page):
        """Header elements remain present in DOM across tab switches."""
        wait_for_dashboard_load(authenticated_page)
        header_selectors = [
            SELECTORS["header"]["reports_btn"],
            SELECTORS["header"]["notification_btn"],
            SELECTORS["header"]["user_menu_btn"],
        ]
        for tab_name in ["command", "federal", "oversight"]:
            switch_to_tab(authenticated_page, tab_name)
            for sel in header_selectors:
                assert authenticated_page.locator(sel).count() == 1, (
                    f"{sel} should be present in DOM on {tab_name} tab"
                )
