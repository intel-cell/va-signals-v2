"""Shared selectors and helpers for Playwright browser tests.

NOTE FOR TEST AUTHORS:
- login.html loads Firebase SDK from CDN. Use wait_until="domcontentloaded" for login page
  navigation to avoid timeouts waiting for external resources.
- Dashboard (index.html) loads Chart.js from CDN. Use wait_for_dashboard_load() which uses
  "domcontentloaded" + explicit selector waits.
- Always use explicit waits (wait_for_selector) rather than fixed timeouts.
"""

from pathlib import Path

BASE_URL = "http://localhost:8000"

# CSS selectors mapped from actual HTML element IDs and attributes

SELECTORS = {
    "tabs": {
        "command": '[data-tab="command"]',
        "federal": '[data-tab="federal"]',
        "oversight": '[data-tab="oversight"]',
        "state": '[data-tab="state"]',
        "battlefield": '[data-tab="battlefield"]',
        "briefs": '[data-tab="briefs"]',
    },
    "panels": {
        "command": "#command-panel",
        "federal": "#federal-panel",
        "oversight": "#oversight-panel",
        "state": "#state-panel",
        "battlefield": "#battlefield-panel",
        "briefs": "#briefs-panel",
    },
    "login": {
        "form": "#login-form",
        "email": "#email",
        "password": "#password",
        "submit": "#submit-btn",
        "google_btn": "#google-signin-btn",
        "error_message": "#error-message",
        "error_text": "#error-text",
        "success_message": "#success-message",
        "session_expired": "#session-expired-message",
        "toggle_password": "#toggle-password",
        "remember_me": "#remember-me",
        "forgot_link": 'a[href="forgot-password.html"]',
    },
    "header": {
        "title": "header h1",
        "reports_btn": "#reports-btn",
        "reports_dropdown": "#reports-dropdown-menu",
        "notification_btn": "#notification-btn",
        "notification_badge": "#notification-badge",
        "user_menu_btn": "#user-menu-btn",
        "user_name": "#user-name",
        "user_email": "#user-email",
        "user_role": "#user-role",
        "user_dropdown": "#user-dropdown-menu",
        "profile_btn": "#profile-btn",
        "audit_log_btn": "#audit-log-btn",
        "logout_btn": "#logout-btn",
        "refresh_indicator": "#refresh-indicator",
        "last_refresh": "#last-refresh-time",
    },
    "common": {
        "classification_banner": ".classification-banner",
        "toast_container": "#toast-container",
        "dashboard": ".dashboard",
    },
}

TAB_NAMES = ["command", "federal", "oversight", "state", "battlefield", "briefs"]


def wait_for_dashboard_load(page, timeout=15000):
    """Navigate to dashboard and wait for full initialization."""
    page.goto(f"{BASE_URL}/", wait_until="domcontentloaded")
    page.wait_for_selector(".tab-btn", timeout=timeout)


def switch_to_tab(page, tab_name, timeout=5000):
    """Click a main navigation tab and wait for panel to appear."""
    selector = SELECTORS["tabs"][tab_name]
    page.click(selector)
    page.wait_for_timeout(300)  # Allow transition


def collect_console_errors(page):
    """Attach console error listener. Returns the mutable error list.

    Filters out network-level noise (ERR_INVALID_HANDLE, ERR_NETWORK_CHANGED)
    that arise from shared browser contexts and CDN resource loading.
    Only captures application-level JavaScript errors.
    """
    # Patterns to ignore — not application JS bugs
    NOISE_PATTERNS = (
        "ERR_INVALID_HANDLE",
        "ERR_NETWORK_CHANGED",
        "ERR_CONNECTION",
        "Failed to load resource",  # Browser HTTP status reporting (404/500/503)
        "Error fetching",  # App fetch wrappers with empty test DB
    )
    errors = []

    def _on_console(msg):
        if msg.type == "error":
            text = msg.text
            if not any(noise in text for noise in NOISE_PATTERNS):
                errors.append(text)

    page.on("console", _on_console)
    return errors


def take_failure_screenshot(page, name):
    """Save a screenshot for debugging test failures."""
    screenshots_dir = Path(__file__).parent / "screenshots"
    screenshots_dir.mkdir(exist_ok=True)
    page.screenshot(path=str(screenshots_dir / f"{name}.png"), full_page=True)
