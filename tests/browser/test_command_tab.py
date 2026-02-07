"""Tests for the Command Center tab content."""

import pytest

from tests.browser.test_utils import (
    SELECTORS,
    wait_for_dashboard_load,
)

pytestmark = pytest.mark.playwright


class TestCommandTab:
    """Verify Command Center panel content and structural elements."""

    def test_command_panel_has_content(self, authenticated_page):
        """Command panel contains child elements (not empty)."""
        wait_for_dashboard_load(authenticated_page)
        panel = authenticated_page.locator(SELECTORS["panels"]["command"])
        children = panel.locator("> *").all()
        assert len(children) > 0, "Command panel should not be empty"

    def test_signal_cards_or_summary(self, authenticated_page):
        """Command panel has mission status cards with stat elements."""
        wait_for_dashboard_load(authenticated_page)
        panel = authenticated_page.locator(SELECTORS["panels"]["command"])
        # Command panel has .command-status-cards section with .status-card elements
        status_cards = panel.locator(".status-card").all()
        assert len(status_cards) >= 4, f"Expected at least 4 status cards, got {len(status_cards)}"
        # Verify key stat IDs exist
        assert authenticated_page.locator("#systems-operational").count() == 1
        assert authenticated_page.locator("#critical-alerts-count").count() == 1
        assert authenticated_page.locator("#pending-actions-count").count() == 1
        assert authenticated_page.locator("#latest-brief-date").count() == 1

    def test_classification_banner_visible(self, authenticated_page):
        """Classification banner shows UNCLASSIFIED text."""
        wait_for_dashboard_load(authenticated_page)
        banner = authenticated_page.locator(SELECTORS["common"]["classification_banner"])
        assert banner.is_visible()
        assert "UNCLASSIFIED" in banner.text_content()

    def test_refresh_indicator_exists(self, authenticated_page):
        """Refresh indicator and last-refresh-time elements exist in header."""
        wait_for_dashboard_load(authenticated_page)
        assert authenticated_page.locator(SELECTORS["header"]["refresh_indicator"]).count() == 1
        assert authenticated_page.locator(SELECTORS["header"]["last_refresh"]).count() == 1

    def test_notification_button_exists(self, authenticated_page):
        """Notification button is present and visible."""
        wait_for_dashboard_load(authenticated_page)
        btn = authenticated_page.locator(SELECTORS["header"]["notification_btn"])
        assert btn.is_visible()

    def test_reports_button_exists(self, authenticated_page):
        """Reports button is present and visible."""
        wait_for_dashboard_load(authenticated_page)
        btn = authenticated_page.locator(SELECTORS["header"]["reports_btn"])
        assert btn.is_visible()
