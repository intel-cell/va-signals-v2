"""Tests for the Briefs tab panel content."""

import pytest

from tests.browser.test_utils import (
    SELECTORS,
    collect_console_errors,
    switch_to_tab,
    wait_for_dashboard_load,
)

pytestmark = pytest.mark.playwright


class TestBriefsTab:
    """Verify Briefs tab renders structural elements correctly."""

    def test_briefs_panel_loads(self, authenticated_page):
        """Briefs panel becomes visible after switching to briefs tab."""
        wait_for_dashboard_load(authenticated_page)
        switch_to_tab(authenticated_page, "briefs")
        authenticated_page.wait_for_timeout(500)
        panel = authenticated_page.locator(SELECTORS["panels"]["briefs"])
        assert panel.is_visible()

    def test_briefs_panel_has_content(self, authenticated_page):
        """Briefs panel contains the brief container with header and sections."""
        wait_for_dashboard_load(authenticated_page)
        switch_to_tab(authenticated_page, "briefs")
        authenticated_page.wait_for_timeout(500)
        # Brief container
        container = authenticated_page.locator("#briefs-panel .brief-container")
        assert container.count() == 1, "Missing .brief-container in briefs panel"
        # Brief header with title
        title = authenticated_page.locator("#briefs-panel .brief-title")
        assert title.count() == 1, "Missing .brief-title"
        # Brief sections (Executive Signal Summary, Federal Register, Congress, etc.)
        sections = authenticated_page.locator("#briefs-panel .brief-section").all()
        assert len(sections) >= 3, f"Expected at least 3 brief sections, got {len(sections)}"

    def test_no_console_errors(self, authenticated_page):
        """No JavaScript console errors on the briefs tab."""
        errors = collect_console_errors(authenticated_page)
        wait_for_dashboard_load(authenticated_page)
        switch_to_tab(authenticated_page, "briefs")
        authenticated_page.wait_for_timeout(1000)
        assert len(errors) == 0, f"Console errors: {errors}"
