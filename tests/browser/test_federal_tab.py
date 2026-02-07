"""Tests for the Federal tab content."""

import pytest

from tests.browser.test_utils import (
    SELECTORS,
    collect_console_errors,
    switch_to_tab,
    wait_for_dashboard_load,
)

pytestmark = pytest.mark.playwright


class TestFederalTab:
    """Verify Federal panel structure: health cards, runs table, documents, hearings, drift."""

    def test_federal_panel_loads(self, authenticated_page):
        """Federal panel becomes visible after switching to the federal tab."""
        wait_for_dashboard_load(authenticated_page)
        switch_to_tab(authenticated_page, "federal")
        assert authenticated_page.locator(SELECTORS["panels"]["federal"]).is_visible()

    def test_federal_panel_has_content(self, authenticated_page):
        """Federal panel has child elements (not empty)."""
        wait_for_dashboard_load(authenticated_page)
        switch_to_tab(authenticated_page, "federal")
        panel = authenticated_page.locator(SELECTORS["panels"]["federal"])
        children = panel.locator("> *").all()
        assert len(children) > 0, "Federal panel should not be empty"

    def test_federal_sub_tabs_if_present(self, authenticated_page):
        """Documents section has FR Documents and eCFR Status sub-tabs."""
        wait_for_dashboard_load(authenticated_page)
        switch_to_tab(authenticated_page, "federal")
        panel = authenticated_page.locator(SELECTORS["panels"]["federal"])
        # Sub-tabs within documents section: data-tab="fr" and data-tab="ecfr"
        fr_sub = panel.locator('[data-tab="fr"]')
        ecfr_sub = panel.locator('[data-tab="ecfr"]')
        assert fr_sub.count() == 1, "FR Documents sub-tab should exist"
        assert ecfr_sub.count() == 1, "eCFR Status sub-tab should exist"

    def test_fr_section_elements(self, authenticated_page):
        """Federal Register section has runs table and FR documents table."""
        wait_for_dashboard_load(authenticated_page)
        switch_to_tab(authenticated_page, "federal")
        panel = authenticated_page.locator(SELECTORS["panels"]["federal"])
        # Runs table
        runs_table = panel.locator("#runs-table")
        assert runs_table.count() == 1, "Runs table should exist in federal panel"
        # FR documents tbody
        fr_tbody = panel.locator("#fr-tbody")
        assert fr_tbody.count() == 1, "FR documents tbody should exist"

    def test_bills_section_elements(self, authenticated_page):
        """VA Legislation section has bills table structure."""
        wait_for_dashboard_load(authenticated_page)
        switch_to_tab(authenticated_page, "federal")
        panel = authenticated_page.locator(SELECTORS["panels"]["federal"])
        bills_table = panel.locator("#bills-table")
        assert bills_table.count() == 1, "Bills table should exist"
        bills_count = panel.locator("#bills-count")
        assert bills_count.count() == 1, "Bills count badge should exist"

    def test_hearings_section_elements(self, authenticated_page):
        """Hearings section has stats and list container."""
        wait_for_dashboard_load(authenticated_page)
        switch_to_tab(authenticated_page, "federal")
        panel = authenticated_page.locator(SELECTORS["panels"]["federal"])
        hearings_list = panel.locator("#hearings-list")
        assert hearings_list.count() == 1, "Hearings list should exist"
        # HVAC/SVAC stat elements
        assert panel.locator("#hearings-hvac").count() == 1, "HVAC stat should exist"
        assert panel.locator("#hearings-svac").count() == 1, "SVAC stat should exist"

    def test_ecfr_section_elements(self, authenticated_page):
        """eCFR sub-tab container and table exist."""
        wait_for_dashboard_load(authenticated_page)
        switch_to_tab(authenticated_page, "federal")
        panel = authenticated_page.locator(SELECTORS["panels"]["federal"])
        ecfr_tab = panel.locator("#ecfr-tab")
        assert ecfr_tab.count() == 1, "eCFR tab content container should exist"
        ecfr_tbody = panel.locator("#ecfr-tbody")
        assert ecfr_tbody.count() == 1, "eCFR tbody should exist"

    def test_no_console_errors(self, authenticated_page):
        """No JavaScript console errors after loading the federal tab."""
        errors = collect_console_errors(authenticated_page)
        wait_for_dashboard_load(authenticated_page)
        switch_to_tab(authenticated_page, "federal")
        authenticated_page.wait_for_timeout(1000)
        assert len(errors) == 0, f"Console errors: {errors}"
