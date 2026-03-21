"""
conftest.py — Playwright fixtures for Taris Bot Web UI tests.

Usage:
    pytest src/tests/ui/ --base-url https://openclawpi2:8080

Environment vars (override defaults):
    PICO_BASE_URL   — default https://openclawpi2:8080
    PICO_ADMIN_USER — default admin
    PICO_ADMIN_PASS — default admin
    PICO_USER       — default stas
    PICO_USER_PASS  — default zusammen20192
"""

import os
import pytest


# ─── Configuration ───────────────────────────────────────────────────────────

BASE_URL    = os.environ.get("PICO_BASE_URL",    "https://openclawpi2:8080")
ADMIN_USER  = os.environ.get("PICO_ADMIN_USER",  "admin")
ADMIN_PASS  = os.environ.get("PICO_ADMIN_PASS",  "admin")
NORMAL_USER = os.environ.get("PICO_USER",        "stas")
NORMAL_PASS = os.environ.get("PICO_USER_PASS",   "zusammen20192")


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
    page.wait_for_url(f"{base_url}/", timeout=10_000)


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
