"""Tests for the State Monitor tab panel content."""

import pytest

from tests.browser.test_utils import (
    SELECTORS,
    collect_console_errors,
    switch_to_tab,
    wait_for_dashboard_load,
)

pytestmark = pytest.mark.playwright


class TestStateTab:
    """Verify State Monitor tab renders structural elements correctly."""

    def test_state_panel_loads(self, authenticated_page):
        """State panel becomes visible after switching to state tab."""
        wait_for_dashboard_load(authenticated_page)
        switch_to_tab(authenticated_page, "state")
        authenticated_page.wait_for_timeout(500)
        panel = authenticated_page.locator(SELECTORS["panels"]["state"])
        assert panel.is_visible()

    def test_state_panel_has_content(self, authenticated_page):
        """State panel contains child elements (health cards, tables)."""
        wait_for_dashboard_load(authenticated_page)
        switch_to_tab(authenticated_page, "state")
        authenticated_page.wait_for_timeout(500)
        panel = authenticated_page.locator(SELECTORS["panels"]["state"])
        children = panel.locator(":scope > *").all()
        assert len(children) > 0, "State panel has no child elements"

    def test_state_filter_elements(self, authenticated_page):
        """State tab has filter buttons for All, TX, CA, FL."""
        wait_for_dashboard_load(authenticated_page)
        switch_to_tab(authenticated_page, "state")
        authenticated_page.wait_for_timeout(500)
        filters = authenticated_page.locator(".state-filter").all()
        assert len(filters) == 4, f"Expected 4 state filter buttons, got {len(filters)}"
        # Verify the "All" filter is active by default
        all_filter = authenticated_page.locator('.state-filter[data-state="all"]')
        assert "active" in all_filter.get_attribute("class")

    def test_state_signals_container(self, authenticated_page):
        """State tab has the signals table with correct column headers."""
        wait_for_dashboard_load(authenticated_page)
        switch_to_tab(authenticated_page, "state")
        authenticated_page.wait_for_timeout(500)
        table = authenticated_page.locator("#state-signals-table")
        assert table.is_visible()
        headers = table.locator("thead th").all()
        header_texts = [h.text_content().strip() for h in headers]
        assert header_texts == ["State", "Severity", "Title", "Source", "Date"]

    def test_state_classification_elements(self, authenticated_page):
        """State tab has severity classification cards (High, Medium, Low, Noise)."""
        wait_for_dashboard_load(authenticated_page)
        switch_to_tab(authenticated_page, "state")
        authenticated_page.wait_for_timeout(500)
        severity_grid = authenticated_page.locator("#severity-grid")
        assert severity_grid.is_visible()
        # Verify individual severity cards exist
        for sev_id in ["sev-high", "sev-medium", "sev-low", "sev-noise"]:
            card = authenticated_page.locator(f"#{sev_id}")
            assert card.count() == 1, f"Missing severity element #{sev_id}"

    def test_state_source_health_elements(self, authenticated_page):
        """State tab has health cards showing total signals, high severity, last run, new (24h)."""
        wait_for_dashboard_load(authenticated_page)
        switch_to_tab(authenticated_page, "state")
        authenticated_page.wait_for_timeout(500)
        health_cards = authenticated_page.locator("#state-panel .health-cards .health-card").all()
        assert len(health_cards) == 4, f"Expected 4 health cards, got {len(health_cards)}"
        # Verify specific card value elements exist
        for card_id in [
            "state-total-signals",
            "state-high-severity",
            "state-last-run",
            "state-new-signals",
        ]:
            el = authenticated_page.locator(f"#{card_id}")
            assert el.count() == 1, f"Missing health card element #{card_id}"

    def test_no_console_errors(self, authenticated_page):
        """No JavaScript console errors on the state tab."""
        errors = collect_console_errors(authenticated_page)
        wait_for_dashboard_load(authenticated_page)
        switch_to_tab(authenticated_page, "state")
        authenticated_page.wait_for_timeout(1000)
        assert len(errors) == 0, f"Console errors: {errors}"
