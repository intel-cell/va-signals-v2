"""Tests for the Oversight Monitor tab content."""

import pytest

from tests.browser.test_utils import (
    SELECTORS,
    collect_console_errors,
    switch_to_tab,
    wait_for_dashboard_load,
)

pytestmark = pytest.mark.playwright


class TestOversightTab:
    """Verify Oversight panel structure: health cards, events table, source breakdown."""

    def test_oversight_panel_loads(self, authenticated_page):
        """Oversight panel becomes visible after switching to the oversight tab."""
        wait_for_dashboard_load(authenticated_page)
        switch_to_tab(authenticated_page, "oversight")
        assert authenticated_page.locator(SELECTORS["panels"]["oversight"]).is_visible()

    def test_oversight_panel_has_content(self, authenticated_page):
        """Oversight panel has child elements (not empty)."""
        wait_for_dashboard_load(authenticated_page)
        switch_to_tab(authenticated_page, "oversight")
        panel = authenticated_page.locator(SELECTORS["panels"]["oversight"])
        children = panel.locator("> *").all()
        assert len(children) > 0, "Oversight panel should not be empty"

    def test_oversight_health_cards(self, authenticated_page):
        """Oversight panel has health cards for events, escalations, deviations, surfaced."""
        wait_for_dashboard_load(authenticated_page)
        switch_to_tab(authenticated_page, "oversight")
        panel = authenticated_page.locator(SELECTORS["panels"]["oversight"])
        # Verify the 4 stat elements exist
        assert panel.locator("#oversight-total-events").count() == 1, (
            "Total events stat should exist"
        )
        assert panel.locator("#oversight-escalations").count() == 1, "Escalations stat should exist"
        assert panel.locator("#oversight-deviations").count() == 1, "Deviations stat should exist"
        assert panel.locator("#oversight-surfaced").count() == 1, "Surfaced stat should exist"

    def test_oversight_events_table(self, authenticated_page):
        """Oversight panel has a Recent Events table with expected columns."""
        wait_for_dashboard_load(authenticated_page)
        switch_to_tab(authenticated_page, "oversight")
        panel = authenticated_page.locator(SELECTORS["panels"]["oversight"])
        events_table = panel.locator("#oversight-events-table")
        assert events_table.count() == 1, "Oversight events table should exist"
        # Verify column headers
        headers = events_table.locator("thead th").all_text_contents()
        expected = ["Source", "Title", "Published", "Escalation", "Deviation", "Surfaced"]
        for col in expected:
            assert col in headers, f"Column '{col}' missing from oversight events table"

    def test_oversight_source_breakdown(self, authenticated_page):
        """Oversight panel has a 'By Source' section with source list container."""
        wait_for_dashboard_load(authenticated_page)
        switch_to_tab(authenticated_page, "oversight")
        panel = authenticated_page.locator(SELECTORS["panels"]["oversight"])
        source_list = panel.locator("#oversight-source-list")
        assert source_list.count() == 1, "Oversight source list should exist"

    def test_no_console_errors(self, authenticated_page):
        """No JavaScript console errors after loading the oversight tab."""
        errors = collect_console_errors(authenticated_page)
        wait_for_dashboard_load(authenticated_page)
        switch_to_tab(authenticated_page, "oversight")
        authenticated_page.wait_for_timeout(1000)
        assert len(errors) == 0, f"Console errors: {errors}"
