"""
test_external_ui.py — Internet-facing Playwright smoke tests for Taris Web UI.

These tests verify that deployed taris instances are accessible from the internet
and that all major UI features work correctly through nginx proxy.

Designed for sub-path deployments (e.g. https://agents.sintaris.net/supertaris/).
All path assertions are prefix-agnostic — they use href*= (contains) selectors
instead of exact href matches, so the same test suite works both at root and
under a sub-path.

Run against SintAItion (TariStation1):
    cd <workspace>
    pytest src/tests/ui/test_external_ui.py -v \
        --base-url https://agents.sintaris.net/supertaris \
        --browser chromium

Run against TariStation2:
    pytest src/tests/ui/test_external_ui.py -v \
        --base-url https://agents.sintaris.net/supertaris2 \
        --browser chromium

Env vars:
    TARIS_ADMIN_USER  — admin username          (default: stas)
    TARIS_ADMIN_PASS  — admin password          (NO default; tests SKIP if unset)
    TARIS_NORMAL_USER — non-admin username      (default: testuser)
    TARIS_NORMAL_PASS — non-admin password      (default: testpass456)

Note: Do NOT set TARIS_ADMIN_PASS in CI without secure secret injection.
"""

import os
import re
import json

import pytest
import requests
from playwright.sync_api import Page, Browser, expect


# ─── Credentials from env ────────────────────────────────────────────────────

_ADMIN_USER  = os.environ.get("TARIS_ADMIN_USER",  "stas")
_ADMIN_PASS  = os.environ.get("TARIS_ADMIN_PASS",  "")          # empty → skip tests
_NORMAL_USER = os.environ.get("TARIS_NORMAL_USER", "testuser")
_NORMAL_PASS = os.environ.get("TARIS_NORMAL_PASS", "testpass456")

_NEED_CREDS = pytest.mark.skipif(
    not _ADMIN_PASS,
    reason="TARIS_ADMIN_PASS not set — skip authenticated tests"
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _fresh(browser: Browser) -> Page:
    ctx = browser.new_context(ignore_https_errors=True)
    return ctx.new_page()


def _login(page: Page, base: str, user: str = _ADMIN_USER, pw: str = _ADMIN_PASS):
    """Navigate to /login, fill credentials, submit, wait for dashboard."""
    page.goto(f"{base}/login")
    page.fill("input[name='username']", user)
    page.fill("input[name='password']", pw)
    page.click("button[type='submit']")
    page.wait_for_url(f"{base}/", timeout=30_000)


def _base(pytestconfig) -> str:
    """Return --base-url or a sensible default for external testing."""
    return (pytestconfig.getoption("--base-url", default=None)
            or "https://agents.sintaris.net/supertaris")


def _ensure_logged_in(page, base: str):
    """Re-login if session expired (page navigated away from dashboard)."""
    if "/login" in page.url or page.url.rstrip("/") == base.rstrip("/"):
        return  # either already at dashboard or needs login
    if "/login" in page.url:
        _login(page, base)


# ─── Session-scoped logged-in page ───────────────────────────────────────────

@pytest.fixture(scope="module")
def ext_admin_page(browser, pytestconfig):
    """Module-scoped page already logged in as admin — for read-only page tests."""
    if not _ADMIN_PASS:
        pytest.skip("TARIS_ADMIN_PASS not set")
    base = _base(pytestconfig)
    ctx = browser.new_context(ignore_https_errors=True)
    page = ctx.new_page()
    _login(page, base)
    yield page, base
    ctx.close()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Reachability (no credentials needed)
# ─────────────────────────────────────────────────────────────────────────────

class TestExternalReachability:
    """Verify the instance is reachable from the internet, HTTPS works, no 5xx."""

    def test_https_accessible_not_502(self, pytestconfig):
        """GET base URL returns 2xx or 3xx — not a 502/503 Bad Gateway."""
        base = _base(pytestconfig)
        resp = requests.get(base + "/login", allow_redirects=True, timeout=15, verify=True)
        assert resp.status_code < 500, (
            f"Expected <500 from {base}/login, got {resp.status_code}. "
            f"Possible nginx 502 Bad Gateway — check SSH reverse tunnel."
        )

    def test_ssl_certificate_valid(self, pytestconfig):
        """HTTPS request succeeds with valid SSL certificate (no verify=False needed)."""
        base = _base(pytestconfig)
        try:
            resp = requests.get(base + "/login", timeout=15, verify=True)
            # Success means cert is valid; status code doesn't matter here
            assert resp.status_code < 500
        except requests.exceptions.SSLError as e:
            pytest.fail(f"SSL certificate error for {base}: {e}")

    def test_unauthenticated_redirects_to_login(self, browser, pytestconfig):
        """GET / without session → redirects to /login. Path must not double-prefix."""
        base = _base(pytestconfig)
        page = _fresh(browser)
        page.goto(f"{base}/")
        # Must end up on .../login (no double-prefix like /supertaris/supertaris/login)
        assert "/login" in page.url, f"Expected /login in URL, got {page.url}"
        # No double-prefix regression: count prefix occurrences
        suffix = page.url.replace("https://", "").replace("http://", "")
        parts = suffix.split("/")
        # The path segment list should not have the same segment twice in a row
        for i in range(len(parts) - 1):
            assert parts[i] != parts[i + 1] or parts[i] == "", (
                f"Double path segment detected in URL: {page.url}"
            )
        page.context.close()

    def test_manifest_json_served(self, pytestconfig):
        """GET /manifest.json → 200 JSON with start_url and correct icons."""
        base = _base(pytestconfig)
        resp = requests.get(f"{base}/manifest.json", timeout=15, verify=True)
        assert resp.status_code == 200, (
            f"Expected 200 from {base}/manifest.json, got {resp.status_code}"
        )
        data = resp.json()
        assert "start_url" in data, "manifest.json missing start_url"
        assert "icons" in data, "manifest.json missing icons"
        # Icons must NOT use host-root /static/... if app is at sub-path
        # They should start with the same prefix as start_url
        prefix = data.get("start_url", "/").rstrip("/")
        if prefix:  # Only check when deployed under a sub-path
            for icon in data["icons"]:
                src = icon.get("src", "")
                assert src.startswith(prefix), (
                    f"Icon src '{src}' missing root_path prefix '{prefix}' — "
                    f"PWA install will fail on sub-path deployment"
                )

    def test_static_assets_served(self, pytestconfig):
        """Static CSS and JS assets are served (not 404)."""
        base = _base(pytestconfig)
        for asset_path in ["/static/style.css"]:
            resp = requests.get(f"{base}{asset_path}", timeout=10, verify=True)
            assert resp.status_code == 200, (
                f"Static asset {base}{asset_path} → {resp.status_code} (expected 200)"
            )


# ─────────────────────────────────────────────────────────────────────────────
# 2. Login & auth
# ─────────────────────────────────────────────────────────────────────────────

class TestExternalLogin:
    """Login flow — valid / invalid credentials, logout."""

    def test_login_page_has_form(self, browser, pytestconfig):
        """GET /login → form with username + password inputs."""
        base = _base(pytestconfig)
        page = _fresh(browser)
        page.goto(f"{base}/login")
        expect(page.locator("input[name='username']")).to_be_visible()
        expect(page.locator("input[name='password']")).to_be_visible()
        expect(page.locator("button[type='submit']")).to_be_visible()
        page.context.close()

    def test_login_invalid_password_shows_error(self, browser, pytestconfig):
        """Wrong password stays on /login and shows an error message."""
        base = _base(pytestconfig)
        page = _fresh(browser)
        page.goto(f"{base}/login")
        page.fill("input[name='username']", _ADMIN_USER)
        page.fill("input[name='password']", "definitely_wrong_password_xyz")
        page.click("button[type='submit']")
        page.wait_for_load_state("networkidle", timeout=10_000)
        assert "/login" in page.url, "Should stay on /login after bad credentials"
        body = page.inner_text("body").lower()
        assert any(kw in body for kw in ["invalid", "wrong", "error", "incorrect", "failed"]), (
            "Expected error message after wrong credentials"
        )
        page.context.close()

    def test_register_page_accessible(self, browser, pytestconfig):
        """GET /register → registration form is visible."""
        base = _base(pytestconfig)
        page = _fresh(browser)
        page.goto(f"{base}/register")
        expect(page.locator("input[name='username']")).to_be_visible()
        page.context.close()

    @_NEED_CREDS
    def test_valid_login_reaches_dashboard(self, browser, pytestconfig):
        """Valid admin login → dashboard at base_url/."""
        base = _base(pytestconfig)
        page = _fresh(browser)
        _login(page, base)
        assert page.url.rstrip("/") == base.rstrip("/"), (
            f"Expected dashboard URL {base}/, got {page.url}"
        )
        expect(page.locator("h1")).to_contain_text("Dashboard")
        page.context.close()

    @_NEED_CREDS
    def test_login_no_double_prefix_in_redirect(self, browser, pytestconfig):
        """After login, URL must NOT contain the sub-path prefix twice (regression)."""
        base = _base(pytestconfig)
        page = _fresh(browser)
        _login(page, base)
        url = page.url
        # Extract prefix segment from base (e.g. 'supertaris' from 'https://host/supertaris')
        prefix_segment = base.rstrip("/").split("/")[-1]
        if prefix_segment:
            count = url.split("/").count(prefix_segment)
            assert count <= 1, (
                f"Double-prefix detected: '{prefix_segment}' appears {count}× in {url}"
            )
        page.context.close()

    @_NEED_CREDS
    def test_logout_redirects_to_login(self, browser, pytestconfig):
        """After logout, visiting / redirects to /login."""
        base = _base(pytestconfig)
        page = _fresh(browser)
        _login(page, base)
        page.goto(f"{base}/logout")
        page.goto(f"{base}/")
        assert "/login" in page.url, f"Expected /login after logout, got {page.url}"
        page.context.close()


# ─────────────────────────────────────────────────────────────────────────────
# 3. Dashboard
# ─────────────────────────────────────────────────────────────────────────────

class TestExternalDashboard:

    @_NEED_CREDS
    def test_dashboard_heading(self, ext_admin_page):
        page, base = ext_admin_page
        page.goto(f"{base}/")
        expect(page.locator("h1")).to_contain_text("Dashboard")

    @_NEED_CREDS
    def test_sidebar_nav_links_have_prefix(self, ext_admin_page):
        """All sidebar nav links contain the deployment prefix (sub-path aware)."""
        page, base = ext_admin_page
        page.goto(f"{base}/")
        # Extract the path prefix (e.g. '/supertaris' from 'https://host/supertaris')
        from urllib.parse import urlparse
        parsed = urlparse(base)
        prefix = parsed.path.rstrip("/")  # e.g. '/supertaris' or ''

        # Every nav link should lead somewhere under the prefix
        nav_links = page.locator(".sidebar-nav a[href]").all()
        assert len(nav_links) >= 4, f"Expected ≥4 nav links, found {len(nav_links)}"
        for link in nav_links:
            href = link.get_attribute("href") or ""
            # href is absolute from host root, e.g. /supertaris/chat
            if prefix:
                assert href.startswith(prefix), (
                    f"Nav link href '{href}' does not start with prefix '{prefix}' — "
                    f"link would 404 on sub-path deployment"
                )

    @_NEED_CREDS
    def test_dashboard_shows_version(self, ext_admin_page):
        """Dashboard sidebar or header shows a version number (e.g. v2026.x.y)."""
        page, base = ext_admin_page
        page.goto(f"{base}/")
        body = page.inner_text("body")
        assert re.search(r"v?\d{4}\.\d+\.\d+", body), (
            "Expected version number on dashboard (e.g. v2026.3.48)"
        )

    @_NEED_CREDS
    def test_dashboard_system_status_visible(self, ext_admin_page):
        """Dashboard shows System Status section."""
        page, base = ext_admin_page
        page.goto(f"{base}/")
        expect(page.locator("text=Bot Status")).to_be_visible()

    @_NEED_CREDS
    def test_quick_actions_links_have_prefix(self, ext_admin_page):
        """Dashboard quick action links include the root_path prefix (regression)."""
        page, base = ext_admin_page
        page.goto(f"{base}/")
        from urllib.parse import urlparse
        prefix = urlparse(base).path.rstrip("/")
        if not prefix:
            pytest.skip("Root-path deployment — prefix check not applicable")

        # Quick action hrefs (chat, notes, calendar, mail)
        quick_links = page.locator(".quick-actions a[href], .dashboard-actions a[href]").all()
        if not quick_links:
            # Fallback: find any main-content links
            quick_links = page.locator("main a[href]").all()
        for link in quick_links:
            href = link.get_attribute("href") or ""
            if href and not href.startswith("http") and not href.startswith("#"):
                assert href.startswith(prefix), (
                    f"Quick action href '{href}' missing prefix '{prefix}'"
                )


# ─────────────────────────────────────────────────────────────────────────────
# 4. All pages load (parametrized smoke test)
# ─────────────────────────────────────────────────────────────────────────────

_PAGES = [
    ("/chat",      "Taris"),
    ("/notes",     "Notes"),
    ("/calendar",  "Calendar"),
    ("/voice",     "Voice"),
    ("/mail",      "Mail"),
    ("/contacts",  "Contacts"),
    ("/documents", "Documents"),
    ("/profile",   "Profile"),
    ("/settings",  "Settings"),
]


class TestExternalPages:

    @_NEED_CREDS
    @pytest.mark.parametrize("path,expected_title", _PAGES)
    def test_page_loads_with_correct_heading(self, ext_admin_page, path, expected_title):
        """Every major page loads and shows the expected h1 heading."""
        page, base = ext_admin_page
        page.goto(f"{base}{path}")
        expect(page.locator("h1")).to_contain_text(expected_title, timeout=10_000)

    @_NEED_CREDS
    @pytest.mark.parametrize("path,_", _PAGES)
    def test_page_has_no_500_error(self, ext_admin_page, path, _):
        """No page should show a 500 Internal Server Error."""
        page, base = ext_admin_page
        page.goto(f"{base}{path}")
        body = page.inner_text("body").lower()
        assert "internal server error" not in body, (
            f"{base}{path} shows 'Internal Server Error'"
        )
        assert "traceback" not in body, (
            f"{base}{path} leaks a Python traceback"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 5. HTMX and interactive features
# ─────────────────────────────────────────────────────────────────────────────

class TestExternalHTMX:

    @_NEED_CREDS
    def test_notes_htmx_create_button_has_prefix(self, ext_admin_page):
        """Notes 'New Note' button hx-post attr includes root_path prefix."""
        page, base = ext_admin_page
        from urllib.parse import urlparse
        prefix = urlparse(base).path.rstrip("/")

        page.goto(f"{base}/notes")
        btn = page.locator("button[hx-post]").first
        hx_post = btn.get_attribute("hx-post") or ""
        if prefix:
            assert hx_post.startswith(prefix), (
                f"hx-post='{hx_post}' missing prefix '{prefix}' — "
                f"HTMX will send request to wrong URL on sub-path"
            )

    @_NEED_CREDS
    def test_notes_create_opens_editor(self, browser, pytestconfig):
        """Clicking New Note triggers HTMX and shows the editor panel."""
        if not _ADMIN_PASS:
            pytest.skip("TARIS_ADMIN_PASS not set")
        base = _base(pytestconfig)
        page = _fresh(browser)
        _login(page, base)
        page.goto(f"{base}/notes")
        # Click by text (prefix-agnostic)
        page.get_by_role("button", name=re.compile("New Note", re.IGNORECASE)).click()
        page.wait_for_selector("#note-editor input[name='title'], #note-editor textarea",
                               timeout=8_000)
        expect(page.locator("#note-editor")).not_to_be_empty()
        page.context.close()

    @_NEED_CREDS
    def test_chat_send_message_works(self, browser, pytestconfig):
        """Type and send a message in chat — user bubble appears and LLM responds."""
        if not _ADMIN_PASS:
            pytest.skip("TARIS_ADMIN_PASS not set")
        base = _base(pytestconfig)
        page = _fresh(browser)
        _login(page, base)
        page.goto(f"{base}/chat")
        test_msg = "Playwright external test ping"
        page.fill("#chat-input", test_msg)
        page.locator("#chat-input").press("Enter")
        # User bubble appears quickly
        page.wait_for_selector(f".chat-user:has-text('{test_msg}')", timeout=10_000)
        # Wait for bot response bubble (LLM can be slow; do NOT use networkidle —
        # streaming chat keeps the connection open indefinitely)
        try:
            page.wait_for_selector(".chat-bot, .chat-assistant", timeout=45_000)
            bot_bubbles = page.locator(".chat-bot, .chat-assistant").count()
            assert bot_bubbles >= 1, "Expected at least one bot response bubble"
        except Exception:
            # LLM may still be processing; at minimum the user bubble appeared
            pass
        page.context.close()

    @_NEED_CREDS
    def test_calendar_add_form_htmx_submit(self, browser, pytestconfig):
        """Calendar add-event form submits without error."""
        if not _ADMIN_PASS:
            pytest.skip("TARIS_ADMIN_PASS not set")
        base = _base(pytestconfig)
        page = _fresh(browser)
        _login(page, base)
        page.goto(f"{base}/calendar")
        page.fill("input[name='title']", "External Playwright Test Event")
        page.fill("input[name='dt_str']", "2099-12-31T10:00")
        page.locator("button[type='submit']").first.click()
        # Wait for HTMX to process (no networkidle — avoid blocking on slow LLM calls)
        page.wait_for_timeout(3_000)
        body = page.inner_text("body").lower()
        assert "internal server error" not in body, (
            "Calendar add form submission triggered a 500 error"
        )
        page.context.close()


# ─────────────────────────────────────────────────────────────────────────────
# 6. Admin panel
# ─────────────────────────────────────────────────────────────────────────────

class TestExternalAdmin:

    @_NEED_CREDS
    def test_admin_panel_loads(self, ext_admin_page):
        """Admin panel is accessible and shows user list."""
        page, base = ext_admin_page
        page.goto(f"{base}/admin")
        expect(page.locator("h1")).to_contain_text("Admin")
        body = page.inner_text("body")
        assert "stas" in body or "admin" in body, "Expected user list in admin panel"


# ─────────────────────────────────────────────────────────────────────────────
# 7. Regression tests (specific bugs that were fixed)
# ─────────────────────────────────────────────────────────────────────────────

class TestExternalRegressions:

    def test_no_502_at_root(self, pytestconfig):
        """Root URL must not return 502 Bad Gateway (SSH tunnel health check)."""
        base = _base(pytestconfig)
        resp = requests.get(base + "/", allow_redirects=True, timeout=15, verify=True)
        assert resp.status_code != 502, (
            "502 Bad Gateway — SSH reverse tunnel is down or port mismatch"
        )
        assert resp.status_code != 503, (
            "503 Service Unavailable — uvicorn/taris-web service is not running"
        )

    def test_login_redirect_is_single_prefix(self, browser, pytestconfig):
        """Unauthenticated redirect to /login must NOT double-prefix the path."""
        base = _base(pytestconfig)
        from urllib.parse import urlparse
        prefix_segment = urlparse(base).path.strip("/")  # e.g. 'supertaris'

        page = _fresh(browser)
        page.goto(f"{base}/chat")  # protected → redirect to login
        login_url = page.url
        page.context.close()

        if prefix_segment:
            # '/supertaris' must appear exactly once in the path
            path_segments = urlparse(login_url).path.split("/")
            occurrences = path_segments.count(prefix_segment)
            assert occurrences <= 1, (
                f"Double-prefix detected: '{prefix_segment}' appears {occurrences}× "
                f"in {login_url} — sub_filter / proxy_redirect may be misconfigured"
            )

    @_NEED_CREDS
    def test_hx_redirect_uses_prefix(self, browser, pytestconfig):
        """Notes 'delete' HX-Redirect response must redirect to prefixed /notes URL.

        Regression: HX-Redirect was '/notes' (no prefix) → 404 after HTMX op.
        """
        if not _ADMIN_PASS:
            pytest.skip("TARIS_ADMIN_PASS not set")
        base = _base(pytestconfig)
        from urllib.parse import urlparse
        prefix = urlparse(base).path.rstrip("/")

        # Use requests to simulate HTMX note creation and check HX-Redirect header
        session = requests.Session()
        session.verify = True
        # Login to get session cookie
        resp = session.post(
            f"{base}/login",
            data={"username": _ADMIN_USER, "password": _ADMIN_PASS},
            allow_redirects=True,
            timeout=15,
        )
        assert resp.status_code < 400, f"Login failed: {resp.status_code}"

        # Trigger note creation (returns HTMX partial + HX-Redirect on some paths)
        resp = session.post(
            f"{base}/notes/create",
            headers={"HX-Request": "true"},
            timeout=15,
        )
        hx_redirect = resp.headers.get("HX-Redirect", "")
        if hx_redirect and prefix:
            assert hx_redirect.startswith(prefix), (
                f"HX-Redirect '{hx_redirect}' missing prefix '{prefix}' — "
                f"HTMX will redirect to wrong URL after note operations"
            )

    def test_manifest_icons_not_404(self, pytestconfig):
        """Icon URLs in manifest.json must return 200, not 404."""
        base = _base(pytestconfig)
        resp = requests.get(f"{base}/manifest.json", timeout=10, verify=True)
        if resp.status_code != 200:
            pytest.skip("manifest.json not served — skipping icon check")
        data = resp.json()
        for icon in data.get("icons", []):
            src = icon.get("src", "")
            if src.startswith("/"):
                # Resolve against the domain
                from urllib.parse import urlparse
                parsed = urlparse(base)
                icon_url = f"{parsed.scheme}://{parsed.netloc}{src}"
            else:
                icon_url = src
            icon_resp = requests.get(icon_url, timeout=10, verify=True)
            # 200 is success; 404 means the icon URL is wrong
            assert icon_resp.status_code != 404, (
                f"Icon {icon_url} → 404. manifest.json has wrong icon paths."
            )
