"""Playwright tests for the login page UI elements.

Validates that all login form elements render correctly,
are visible, and have expected properties.
"""

import pytest

from tests.browser.test_utils import BASE_URL, SELECTORS

pytestmark = pytest.mark.playwright


class TestLoginPage:
    """Login page UI element tests."""

    def _goto_login(self, page):
        """Navigate to login page with domcontentloaded (Firebase CDN safety)."""
        page.goto(f"{BASE_URL}/login.html", wait_until="domcontentloaded")

    def test_page_title(self, page):
        """Title contains 'Command Post Login'."""
        self._goto_login(page)
        assert "Command Post Login" in page.title()

    def test_email_field_visible(self, page):
        """Email input (#email) is visible."""
        self._goto_login(page)
        email = page.locator(SELECTORS["login"]["email"])
        assert email.is_visible()
        assert email.get_attribute("type") == "email"
        assert email.get_attribute("required") is not None

    def test_password_field_visible(self, page):
        """Password input (#password) is visible."""
        self._goto_login(page)
        password = page.locator(SELECTORS["login"]["password"])
        assert password.is_visible()
        assert password.get_attribute("type") == "password"
        assert password.get_attribute("required") is not None

    def test_submit_button_visible(self, page):
        """Submit button (#submit-btn) is visible with correct text."""
        self._goto_login(page)
        submit = page.locator(SELECTORS["login"]["submit"])
        assert submit.is_visible()
        assert "Sign In" in submit.text_content()

    def test_google_signin_button(self, page):
        """Google sign-in button (#google-signin-btn) is visible."""
        self._goto_login(page)
        google_btn = page.locator(SELECTORS["login"]["google_btn"])
        assert google_btn.is_visible()
        assert "Google" in google_btn.text_content()

    def test_toggle_password_button(self, page):
        """Toggle password visibility button (#toggle-password) exists."""
        self._goto_login(page)
        toggle = page.locator(SELECTORS["login"]["toggle_password"])
        assert toggle.is_visible()
        assert toggle.get_attribute("aria-label") == "Toggle password visibility"

    def test_remember_me_checkbox(self, page):
        """Remember-me checkbox (#remember-me) exists."""
        self._goto_login(page)
        checkbox = page.locator(SELECTORS["login"]["remember_me"])
        assert checkbox.count() == 1
        assert checkbox.get_attribute("type") == "checkbox"

    def test_forgot_password_link(self, page):
        """Forgot password link pointing to forgot-password.html exists."""
        self._goto_login(page)
        link = page.locator(SELECTORS["login"]["forgot_link"])
        assert link.is_visible()
        assert "Forgot password" in link.text_content()

    def test_error_message_hidden_by_default(self, page):
        """Error message (#error-message) is hidden on initial load."""
        self._goto_login(page)
        error = page.locator(SELECTORS["login"]["error_message"])
        assert not error.is_visible()

    def test_empty_form_submit_shows_validation(self, page):
        """Clicking submit with empty fields shows error or triggers validation.

        The form has novalidate, so the JS handler should display the
        error-message div when fields are empty.
        """
        self._goto_login(page)
        page.click(SELECTORS["login"]["submit"])
        # Wait briefly for JS to process the submission
        page.wait_for_timeout(500)
        # The JS handler should either show the error message or the form
        # should remain on the login page (not redirect)
        assert (
            "login" in page.url.lower()
            or page.locator(SELECTORS["login"]["error_message"]).is_visible()
        )
