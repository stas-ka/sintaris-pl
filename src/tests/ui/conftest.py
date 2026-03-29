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
            _load_accounts, _save_accounts, create_account
        )
        import bcrypt

        def _ensure(uname, upass, role):
            """Ensure account exists with correct pw_hash, role, status."""
            accs = _load_accounts()
            target = next((a for a in accs if a.get("username") == uname.lower()), None)
            if target is None:
                create_account(uname, upass, role=role,
                               display_name=uname.capitalize(), status="active")
                return
            # Update in-place if needed
            changed = False
            if not target.get("pw_hash"):
                target["pw_hash"] = bcrypt.hashpw(
                    upass.encode(), bcrypt.gensalt(rounds=10)
                ).decode()
                changed = True
            if role == "user" and target.get("role") in ("admin", "developer"):
                target["role"] = "user"
                changed = True
            if target.get("status") != "active":
                target["status"] = "active"
                changed = True
            if changed:
                _save_accounts(accs)

        _ensure(ADMIN_USER, ADMIN_PASS, "admin")
        _ensure(NORMAL_USER, NORMAL_PASS, "user")
    except Exception as e:
        print(f"[conftest] WARNING: could not ensure test accounts: {e}")

# ─── Playwright launch options ───────────────────────────────────────────────

@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Ignore self-signed TLS cert on Pi2."""
    return {
        **browser_context_args,
        "ignore_https_errors": True,
    }


# ─── Shared page helpers ──────────────────────────────────────────────────────

def login(page, username: str, password: str, base_url: str = BASE_URL):
    """Navigate to /login, fill credentials, submit and wait for redirect."""
    page.goto(f"{base_url}/login")
    page.fill("input[name='username']", username)
    page.fill("input[name='password']", password)
    page.click("button[type='submit']")
    page.wait_for_url(f"{base_url}/", timeout=30_000)


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
