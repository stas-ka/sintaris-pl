---
mode: agent
description: Run and extend Web UI (Playwright) and Telegram smoke tests. Use playwright-mcp live browser inspection to detect untested routes and add missing test coverage.
---

# Test UI (`/taris_test_ui`)

**Usage**: `/taris_test_ui [scope]`

| Parameter | Values | Default |
|---|---|---|
| `scope` | `web` \| `telegram` \| `coverage` \| `update` \| `all` | `all` |

- `web` — run existing pytest-playwright test suite only
- `telegram` — run Telegram bot smoke tests only
- `coverage` — inspect live UI with playwright-mcp and report untested routes
- `update` — inspect live UI and extend `test_ui.py` with new test functions
- `all` — run all existing tests, then report coverage gaps

---

## Prerequisites

```bat
pip install pytest playwright pytest-playwright
playwright install chromium
```

Credentials come from environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `PICO_BASE_URL` | `https://openclawpi2:8080` | Target Pi2 Web UI |
| `PICO_ADMIN_USER` | `admin` | Admin username |
| `PICO_ADMIN_PASS` | `admin` | Admin password |
| `PICO_USER` | `stas` | Normal user username |
| `PICO_USER_PASS` | `zusammen20192` | Normal user password |
| `HOSTPWD` | (from `.env`) | PI1 SSH password |
| `HOSTPWD2` | (from `.env`) | PI2 SSH password |

---

## Step 1 — Run existing Web UI tests (scope: `web` / `all`)

```bat
rem Standard run — all web tests against PI2
py -m pytest src/tests/ui/test_ui.py -v --base-url https://openclawpi2:8080 --browser chromium

rem Run a single test class
py -m pytest src/tests/ui/test_ui.py -v -k "TestAuth"

rem Run with specific base URL override
set PICO_BASE_URL=https://openclawpi2:8080
py -m pytest src/tests/ui/ -v

rem Run with detailed failure output
py -m pytest src/tests/ui/test_ui.py -v --tb=short --browser chromium --base-url https://openclawpi2:8080
```

### Test class reference

| ID | Class | Routes tested | Admin? |
|---|---|---|---|
| T01 | `TestAuth` | `/login`, `/logout` | No |
| T02 | `TestDashboard` | `/` | No |
| T03 | `TestChat` | `/chat`, `/chat/send`, `/chat/clear` | No |
| T04 | `TestNotes` | `/notes`, `/notes/{slug}` | No |
| T05 | `TestCalendar` | `/calendar`, `/calendar/add`, `/calendar/parse-text`, `/calendar/console` | No |
| T06 | `TestVoice` | `/voice`, `/voice/tts` | No |
| T07 | `TestMail` | `/mail` | No |
| T08 | `TestAdmin` | `/admin`, `/admin/llm/{model_name}` | Admin |
| T09 | `TestNavigation` | all nav links | No |
| T10 | `TestRegistration` | `/register` | No |
| T11 | `TestProfile` | `/profile` | No |
| T12 | `TestSettings` | `/settings`, `/settings/language`, `/settings/password` | No — **NOT YET IMPLEMENTED** |
| T13 | `TestContacts` | `/contacts`, `/contacts/new`, `/contacts/{cid}`, `/contacts/{cid}/delete` | No — **NOT YET IMPLEMENTED** |

### Pass/Fail rules

| Result | Meaning | Action |
|---|---|---|
| PASSED | Test completed without assertion errors | No action |
| FAILED | Assertion error or element not found | Check route is deployed; re-run single class |
| ERROR | Test runner / import error | Check dependencies, `conftest.py` |
| XFAIL | Expected failure (marked `pytest.mark.xfail`) | No action |

**All tests must PASS before marking a deployment complete.**

---

## Step 2 — Run Telegram smoke tests (scope: `telegram` / `all`)

```bat
rem Telegram bot service journal — verify version + polling started
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "journalctl -u picoclaw-telegram -n 20 --no-pager"
plink -pw "%HOSTPWD2%" -batch stas@OpenClawPI2 "journalctl -u picoclaw-telegram -n 20 --no-pager"
```

**Expected journal output (PASS):**
```
[INFO] Version      : 2026.X.Y
[INFO] DB init OK   : /home/stas/.picoclaw/pico.db
[INFO] Polling Telegram…
```

Any `ERROR` or `Traceback` in the last 20 lines = FAIL. Check the failing service and redeploy.

```bat
rem Web service smoke check
plink -pw "%HOSTPWD2%" -batch stas@OpenClawPI2 "journalctl -u picoclaw-web -n 20 --no-pager"
```

**Expected (PASS):** `Uvicorn running on https://0.0.0.0:8080`

---

## Step 3 — Live coverage audit with playwright-mcp (scope: `coverage` / `update`)

Load playwright-mcp tools first (search `playwright` in tool registry).

### 3a — Login to live PI2

```
# Navigate to login page
mcp_playwright_browser_navigate: https://openclawpi2:8080/login

# Fill login form
mcp_playwright_browser_fill_form: {email/username: "admin", password: "admin"}

# Click submit / take snapshot to confirm logged in
mcp_playwright_browser_snapshot
```

### 3b — Inspect uncovered routes

For each route in the **NOT COVERED** list below, navigate to it and take a snapshot:

```
mcp_playwright_browser_navigate: https://openclawpi2:8080/settings
mcp_playwright_browser_snapshot
```

```
mcp_playwright_browser_navigate: https://openclawpi2:8080/contacts
mcp_playwright_browser_snapshot
```

```
mcp_playwright_browser_navigate: https://openclawpi2:8080/contacts/new
mcp_playwright_browser_snapshot
```

**From each snapshot, extract:**
- Page title / heading text
- Input field IDs or `name` attributes
- Button IDs or `type="submit"` attributes
- Key section IDs (`#settings-form`, `#contact-list`, etc.)

Record these selectors — they are needed to write test assertions.

### 3c — Known coverage gaps (routes with NO tests in `test_ui.py`)

| Route | HTTP | Priority | Notes |
|---|---|---|---|
| `/settings` | GET | 🔴 High | Language selector + password change form — entirely untested |
| `/settings/language` | POST | 🔴 High | Language save HTMX endpoint |
| `/settings/password` | POST | 🔴 High | Password change endpoint |
| `/contacts` | GET | 🔴 High | Contact book list — entire feature untested |
| `/contacts/new` | GET+POST | 🔴 High | Create contact form |
| `/contacts/{cid}` | GET+POST | 🔴 High | View/edit contact |
| `/contacts/{cid}/delete` | POST | 🔴 High | Delete contact |
| `/profile/name` | POST | 🟡 Medium | Profile name update (form present in TestProfile, action not tested) |
| `/notes/{slug}/save` | POST | 🟡 Medium | Note save button not exercised |
| `/notes/{slug}` (DELETE) | DELETE | 🟡 Medium | Delete note HTMX action |
| `/calendar/{ev_id}/delete` | POST | 🟡 Medium | Delete event not exercised |
| `/voice/tts` | POST | 🟡 Medium | TTS synthesis endpoint |
| `/voice/transcribe` | POST | 🟡 Medium | File upload STT endpoint |
| `/admin/voice-opt/{key}` | POST | 🟢 Low | Toggle flag via admin panel |
| `/admin/user/{user_id}/approve` | POST | 🟢 Low | Approve pending user |
| `/admin/user/{user_id}/block` | POST | 🟢 Low | Block user |
| `/mail/refresh` | POST | 🟢 Low | Trigger IMAP refresh |
| `/mail/settings` | POST | 🟢 Low | Save IMAP credentials |
| `/mail/settings/delete` | POST | 🟢 Low | Delete IMAP credentials |

---

## Step 4 — Add new test classes (scope: `update`)

After gathering selectors via playwright-mcp in Step 3, add new test classes to `src/tests/ui/test_ui.py`. Follow the exact patterns used by existing classes.

### TestSettings scaffold

```python
class TestSettings:
    """Tests for /settings — language selector and password change."""

    def test_settings_page_loads(self, user_page, base_url):
        """GET /settings returns 200 and shows the settings form."""
        user_page.goto(f"{base_url}/settings")
        assert user_page.url.endswith("/settings") or "/settings" in user_page.url
        # Replace #settings-form with selector found via playwright-mcp snapshot:
        assert user_page.locator("#settings-form").is_visible()

    def test_language_selector_present(self, user_page, base_url):
        """Settings page has a language dropdown."""
        user_page.goto(f"{base_url}/settings")
        # Replace #language-select with actual selector from snapshot:
        assert user_page.locator("select[name='language']").count() > 0

    def test_password_form_present(self, user_page, base_url):
        """Settings page has current/new password inputs."""
        user_page.goto(f"{base_url}/settings")
        # Confirm by snapshot which names/ids are used:
        assert user_page.locator("input[type='password']").count() >= 2
```

### TestContacts scaffold

```python
class TestContacts:
    """Tests for /contacts — contact book CRUD."""

    def test_contacts_page_loads(self, user_page, base_url):
        """GET /contacts returns 200."""
        user_page.goto(f"{base_url}/contacts")
        assert user_page.url.endswith("/contacts") or "/contacts" in user_page.url

    def test_contacts_list_visible(self, user_page, base_url):
        """Contacts page renders a list container."""
        user_page.goto(f"{base_url}/contacts")
        # Replace with selector from snapshot:
        assert user_page.locator("#contact-list, .contacts-list").count() > 0

    def test_new_contact_form_loads(self, user_page, base_url):
        """GET /contacts/new returns the create form."""
        user_page.goto(f"{base_url}/contacts/new")
        # Replace with selector from snapshot:
        assert user_page.locator("form").count() > 0
        assert user_page.locator("input[name='name'], input[name='first_name']").count() > 0

    def test_create_contact_button_present(self, user_page, base_url):
        """Contacts page has a create/add button."""
        user_page.goto(f"{base_url}/contacts")
        # Replace with selector from snapshot:
        assert user_page.locator("a[href*='/contacts/new'], button:has-text('Add')").count() > 0
```

**Critical rule for selectors:** Always use the exact `id` or `name` attributes observed via `mcp_playwright_browser_snapshot` — never guess. If the snapshot shows `id="contact-table"` use that; do not assume `#contact-list`.

---

## Step 5 — Run updated tests to confirm

After adding new test classes:

```bat
rem Run only the new classes
py -m pytest src/tests/ui/test_ui.py -v -k "TestSettings or TestContacts" --base-url https://openclawpi2:8080 --browser chromium

rem Full suite smoke check
py -m pytest src/tests/ui/test_ui.py -v --base-url https://openclawpi2:8080 --browser chromium
```

All new tests must PASS before committing.

---

## Step 6 — Update doc/test-suite.md

After adding new test classes, update the table in `doc/test-suite.md` §3.3:

| Class | Tests | What it validates |
|---|---|---|
| `TestSettings` | N tests | `/settings` page, language selector, password form |
| `TestContacts` | N tests | `/contacts` list, `/contacts/new` form, create button |

---

## Quick scope guide

| Scope | Steps to run |
|---|---|
| `web` | Step 1 only |
| `telegram` | Step 2 only |
| `coverage` | Steps 3b + 3c (report gaps, do not modify tests) |
| `update` | Steps 3a → 3c → 4 → 5 → 6 |
| `all` | Steps 1 → 2 → 3b → 3c (report gaps) |
