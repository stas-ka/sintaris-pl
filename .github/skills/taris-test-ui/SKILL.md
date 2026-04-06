---
name: taris-test-ui
description: >
  Run and extend Web UI (Playwright) and Telegram smoke tests. Use
  playwright-mcp live browser inspection to detect untested routes and
  add missing test coverage.
argument-hint: >
  scope: web | telegram | coverage | update | all (default: all)
---

## Prerequisites

```bash
pip install pytest playwright pytest-playwright
playwright install chromium
```

| Variable | Default | Purpose |
|---|---|---|
| `PICO_BASE_URL` | `https://openclawpi2:8080` | Target Web UI |
| `PICO_ADMIN_USER` | `admin` | Admin username |
| `PICO_ADMIN_PASS` | `admin` | Admin password |
| `PICO_USER` | `stas` | Normal user |
| `PICO_USER_PASS` | (from `.env`) | Normal user password |

---

## scope: `web` — Run existing Playwright suite

```bash
# Standard run against PI2
python3 -m pytest src/tests/ui/test_ui.py -v \
  --base-url https://openclawpi2:8080 --browser chromium

# Single class
python3 -m pytest src/tests/ui/test_ui.py -v -k "TestAuth" \
  --base-url https://openclawpi2:8080 --browser chromium

# Against local TariStation2
python3 -m pytest src/tests/ui/test_ui.py -v \
  --base-url http://localhost:8080 --browser chromium
```

### Test class reference

| ID | Class | Routes tested |
|---|---|---|
| T01 | `TestAuth` | `/login`, `/logout` |
| T02 | `TestDashboard` | `/` |
| T03 | `TestChat` | `/chat`, `/chat/send`, `/chat/clear` |
| T04 | `TestNotes` | `/notes`, `/notes/{slug}` |
| T05 | `TestCalendar` | `/calendar`, `/calendar/add`, `/calendar/parse-text` |
| T06 | `TestVoice` | `/voice`, `/voice/tts` |
| T07 | `TestMail` | `/mail` |
| T08 | `TestAdmin` | `/admin`, `/admin/llm/{model}` |
| T09 | `TestNavigation` | all nav links |
| T10 | `TestRegistration` | `/register` |
| T11 | `TestProfile` | `/profile` |

---

## scope: `telegram` — Smoke tests

```bash
# Verify journal shows version + polling
plink -pw "$HOSTPWD" -batch stas@OpenClawPI \
  "journalctl -u taris-telegram -n 20 --no-pager"
plink -pw "$HOSTPWD2" -batch stas@OpenClawPI2 \
  "journalctl -u taris-telegram -n 20 --no-pager"

# Web service check
plink -pw "$HOSTPWD2" -batch stas@OpenClawPI2 \
  "journalctl -u taris-web -n 20 --no-pager"
```

**PASS:** `[INFO] Version : 2026.X.Y` + `[INFO] Polling Telegram…`  
**FAIL:** Any `ERROR` or `Traceback` in last 20 lines.

---

## scope: `coverage` — Audit untested routes

Use playwright-mcp to navigate live UI and report gaps:

```
# Login
mcp_playwright_browser_navigate: https://openclawpi2:8080/login
mcp_playwright_browser_fill_form: {username: "admin", password: "admin"}
mcp_playwright_browser_snapshot

# Navigate to each uncovered route and snapshot
mcp_playwright_browser_navigate: https://openclawpi2:8080/settings
mcp_playwright_browser_snapshot
```

### Known coverage gaps (no tests yet)

| Route | Priority | Notes |
|---|---|---|
| `/settings` GET/POST | 🔴 High | Language + password form |
| `/settings/language` POST | 🔴 High | Language save HTMX endpoint |
| `/settings/password` POST | 🔴 High | Password change |
| `/contacts` GET | 🔴 High | Contact book list |
| `/contacts/new` GET+POST | 🔴 High | Create contact |
| `/contacts/{cid}` GET+POST | 🔴 High | View/edit contact |
| `/contacts/{cid}/delete` POST | 🔴 High | Delete contact |
| `/notes/{slug}/save` POST | 🟡 Medium | Note save button |
| `/calendar/{ev_id}/delete` POST | 🟡 Medium | Delete event |
| `/voice/transcribe` POST | 🟡 Medium | File upload STT |
| `/admin/voice-opt/{key}` POST | 🟢 Low | Toggle flag |
| `/admin/user/{id}/approve` POST | 🟢 Low | Approve user |

---

## scope: `update` — Add new tests

After inspecting live routes via playwright-mcp, add test classes to `src/tests/ui/test_ui.py`.

**Rule:** Use **exact** selectors from `mcp_playwright_browser_snapshot` — never guess.

Example scaffold:
```python
class TestSettings:
    def test_settings_page_loads(self, user_page, base_url):
        user_page.goto(f"{base_url}/settings")
        assert "/settings" in user_page.url
        # Use selector from snapshot (e.g. id="settings-form"):
        assert user_page.locator("#settings-form").is_visible()
```

After adding classes:
```bash
python3 -m pytest src/tests/ui/test_ui.py -v -k "TestSettings" \
  --base-url https://openclawpi2:8080 --browser chromium
```

All new tests must PASS before committing.

Update `doc/test-suite.md` §3.3 with the new class entry.

---

## Pass / Fail Rules

| Result | Meaning | Action |
|---|---|---|
| PASSED | Assertion passed | No action |
| FAILED | Element not found / assertion error | Check route deployed; re-run single class |
| ERROR | Import/runner error | Check dependencies, `conftest.py` |
| XFAIL | Expected failure | No action |

**All tests must PASS before marking a deployment complete.**
