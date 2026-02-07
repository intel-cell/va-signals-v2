"""Tests for the Battlefield tab panel content."""

import pytest

from tests.browser.test_utils import (
    SELECTORS,
    collect_console_errors,
    switch_to_tab,
    wait_for_dashboard_load,
)

pytestmark = pytest.mark.playwright


class TestBattlefieldTab:
    """Verify Battlefield tab renders structural elements correctly."""

    def test_battlefield_panel_loads(self, authenticated_page):
        """Battlefield panel becomes visible after switching to battlefield tab."""
        wait_for_dashboard_load(authenticated_page)
        switch_to_tab(authenticated_page, "battlefield")
        authenticated_page.wait_for_timeout(500)
        panel = authenticated_page.locator(SELECTORS["panels"]["battlefield"])
        assert panel.is_visible()

    def test_battlefield_panel_has_content(self, authenticated_page):
        """Battlefield panel contains child elements (health cards, tables, actions)."""
        wait_for_dashboard_load(authenticated_page)
        switch_to_tab(authenticated_page, "battlefield")
        authenticated_page.wait_for_timeout(500)
        panel = authenticated_page.locator(SELECTORS["panels"]["battlefield"])
        children = panel.locator(":scope > *").all()
        assert len(children) > 0, "Battlefield panel has no child elements"

    def test_battlefield_gate_elements(self, authenticated_page):
        """Battlefield tab has critical gates table, vehicles table, and alerts table."""
        wait_for_dashboard_load(authenticated_page)
        switch_to_tab(authenticated_page, "battlefield")
        authenticated_page.wait_for_timeout(500)
        # Critical Gates table
        critical_table = authenticated_page.locator("#bf-critical-table")
        assert critical_table.count() == 1, "Missing critical gates table"
        critical_headers = critical_table.locator("thead th").all()
        critical_texts = [h.text_content().strip() for h in critical_headers]
        assert critical_texts == ["Date", "Vehicle", "Event", "Days", "Importance", "Action"]
        # Active Vehicles table
        vehicles_table = authenticated_page.locator("#bf-vehicles-table")
        assert vehicles_table.count() == 1, "Missing vehicles table"
        # Alerts table
        alerts_table = authenticated_page.locator("#bf-alerts-table")
        assert alerts_table.count() == 1, "Missing alerts table"
        # Health cards
        for card_id in ["bf-total-vehicles", "bf-gates-14d", "bf-alerts-48h", "bf-unack-alerts"]:
            el = authenticated_page.locator(f"#{card_id}")
            assert el.count() == 1, f"Missing battlefield health card #{card_id}"
        # Action buttons
        actions = authenticated_page.locator(".battlefield-actions button").all()
        assert len(actions) == 2, (
            f"Expected 2 action buttons (Sync Sources, Run Detection), got {len(actions)}"
        )

    def test_no_console_errors(self, authenticated_page):
        """No JavaScript console errors on the battlefield tab."""
        errors = collect_console_errors(authenticated_page)
        wait_for_dashboard_load(authenticated_page)
        switch_to_tab(authenticated_page, "battlefield")
        authenticated_page.wait_for_timeout(1000)
        assert len(errors) == 0, f"Console errors: {errors}"
