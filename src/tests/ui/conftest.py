"""
conftest.py — Playwright fixtures for Taris Bot Web UI tests.

Usage:
    pytest src/tests/ui/ --base-url https://openclawpi2:8080

Environment vars (override defaults):
    PICO_BASE_URL   — default https://openclawpi2:8080
    PICO_ADMIN_USER — default admin
    PICO_ADMIN_PASS — default admin
    PICO_USER       — default testuser  (non-admin, auto-created if absent)
    PICO_USER_PASS  — default testpass456
"""

import os
import pytest


# ─── Configuration ───────────────────────────────────────────────────────────

BASE_URL    = os.environ.get("PICO_BASE_URL",    "https://openclawpi2:8080")
ADMIN_USER  = os.environ.get("PICO_ADMIN_USER",  "admin")
ADMIN_PASS  = os.environ.get("PICO_ADMIN_PASS",  "admin")
NORMAL_USER = os.environ.get("PICO_USER",        "testuser")
NORMAL_PASS = os.environ.get("PICO_USER_PASS",   "testpass456")


# ─── Ensure test accounts exist before any test runs ─────────────────────────

@pytest.fixture(scope="session", autouse=True)
def ensure_test_accounts():
    """Create/update test accounts in accounts.json so all tests can log in."""
    import sys, os as _os
    _src = _os.path.join(_os.path.dirname(__file__), "..", "..")
    if _src not in sys.path:
        sys.path.insert(0, _src)
    try:
        from security.bot_auth import (
            create_account, update_account, find_account_by_username, change_password
        )

        def _ensure(uname, upass, role):
            """Ensure test account exists with exact pw_hash, role, and status."""
            existing = find_account_by_username(uname.lower())
            if existing is None:
                create_account(uname, upass, role=role,
                               display_name=uname.capitalize(), status="active")
            else:
                # Reset to known credentials so tests are deterministic
                change_password(existing["user_id"], upass)
                update_account(existing["user_id"], role=role, status="active")

        _ensure(ADMIN_USER, ADMIN_PASS, "admin")
        _ensure(NORMAL_USER, NORMAL_PASS, "user")
    except Exception as e:
        print(f"[conftest] WARNING: could not ensure test accounts: {e}")

# ─── Playwright launch options ───────────────────────────────────────────────

@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    """Add --no-sandbox for CI/cloud environments where sandbox is not available."""
    return {
        **browser_type_launch_args,
        "args": browser_type_launch_args.get("args", []) + ["--no-sandbox", "--disable-dev-shm-usage"],
    }


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Ignore self-signed TLS cert on Pi2."""
    return {
        **browser_context_args,
        "ignore_https_errors": True,
    }


# ─── Shared page helpers ──────────────────────────────────────────────────────

def login(page, username: str, password: str, base_url: str = BASE_URL):
    """Authenticate and set the auth cookie in the Playwright context.

    Uses requests to POST /login directly (bypassing the browser form submission)
    because the rendered form action uses ROOT_PATH prefix that may not resolve
    on direct localhost access. The cookie is then injected into Playwright.
    """
    import requests
    import urllib.parse

    parsed = urllib.parse.urlparse(base_url)
    hostname = parsed.hostname  # e.g. "localhost"

    # POST credentials directly — this always works regardless of ROOT_PATH
    resp = requests.post(
        f"{base_url}/login",
        data={"username": username, "password": password},
        verify=False,
        allow_redirects=False,
        timeout=10,
    )
    if resp.status_code not in (302, 303, 200):
        raise RuntimeError(
            f"Login POST failed for {username!r}: HTTP {resp.status_code}"
        )

    # Inject all cookies from the response into the Playwright context
    for cookie in resp.cookies:
        page.context.add_cookies([{
            "name": cookie.name,
            "value": cookie.value,
            "domain": hostname,
            "path": cookie.path or "/",
        }])

    # Navigate to the app root — auth cookie is now set
    page.goto(f"{base_url}/", wait_until="domcontentloaded", timeout=15_000)
    if "/login" in page.url:
        raise RuntimeError(
            f"Login failed for {username!r} — still on login page after auth: {page.url}"
        )


# ─── Session-scoped authenticated contexts ───────────────────────────────────

@pytest.fixture(scope="session")
def admin_page(browser, base_url_or_default):
    """A browser page already logged in as admin for the whole session."""
    context = browser.new_context(ignore_https_errors=True)
    page = context.new_page()
    login(page, ADMIN_USER, ADMIN_PASS, base_url_or_default)
    yield page
    context.close()


@pytest.fixture(scope="session")
def user_page(browser, base_url_or_default):
    """A browser page already logged in as a regular user for the whole session."""
    context = browser.new_context(ignore_https_errors=True)
    page = context.new_page()
    login(page, NORMAL_USER, NORMAL_PASS, base_url_or_default)
    yield page
    context.close()


@pytest.fixture(scope="session")
def base_url_or_default(pytestconfig):
    """Return --base-url CLI arg or the default BASE_URL."""
    cli = pytestconfig.getoption("--base-url", default=None)
    return cli or BASE_URL
