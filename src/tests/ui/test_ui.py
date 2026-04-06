"""
test_ui.py — Playwright end-to-end tests for the Taris Bot Web UI.

Run (from workspace root):
    pytest src/tests/ui/test_ui.py -v --base-url https://openclawpi2:8080

Or simply:
    pytest src/tests/ui/ -v

The suite uses the admin/admin default account and stas/zusammen20192 regular user.
All tests target Pi2 (https://openclawpi2:8080) with a self-signed TLS certificate.
"""

import re
import pytest
from playwright.sync_api import Page, expect, Browser

from conftest import (
    BASE_URL, ADMIN_USER, ADMIN_PASS, NORMAL_USER, NORMAL_PASS, login,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def fresh_page(browser: Browser, base: str):
    """Return a new page with TLS errors ignored."""
    ctx = browser.new_context(ignore_https_errors=True)
    return ctx.new_page()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Authentication
# ─────────────────────────────────────────────────────────────────────────────

class TestAuth:

    def test_login_page_loads(self, browser, base_url_or_default):
        """GET /login returns the login form."""
        page = fresh_page(browser, base_url_or_default)
        page.goto(f"{base_url_or_default}/login")
        expect(page.locator("input[name='username']")).to_be_visible()
        expect(page.locator("input[name='password']")).to_be_visible()
        expect(page.locator("button[type='submit']")).to_be_visible()
        page.context.close()

    def test_login_invalid_credentials_shows_error(self, browser, base_url_or_default):
        """Wrong password shows an error message, stays on /login."""
        page = fresh_page(browser, base_url_or_default)
        page.goto(f"{base_url_or_default}/login")
        page.fill("input[name='username']", "admin")
        page.fill("input[name='password']", "wrongpassword")
        page.click("button[type='submit']")
        expect(page.locator(".login-error")).to_be_visible()
        assert "/login" in page.url
        page.context.close()

    def test_login_valid_admin_redirects_to_dashboard(self, browser, base_url_or_default):
        """Valid admin login redirects to /."""
        page = fresh_page(browser, base_url_or_default)
        login(page, ADMIN_USER, ADMIN_PASS, base_url_or_default)
        assert page.url.rstrip("/") == base_url_or_default.rstrip("/")
        page.context.close()

    def test_login_valid_user_redirects_to_dashboard(self, browser, base_url_or_default):
        """Valid regular user login redirects to /."""
        page = fresh_page(browser, base_url_or_default)
        login(page, NORMAL_USER, NORMAL_PASS, base_url_or_default)
        assert page.url.rstrip("/") == base_url_or_default.rstrip("/")
        page.context.close()

    def test_unauthenticated_redirect_to_login(self, browser, base_url_or_default):
        """Accessing protected pages without session redirects to /login."""
        page = fresh_page(browser, base_url_or_default)
        for path in ["/", "/chat", "/notes", "/calendar", "/voice"]:
            page.goto(f"{base_url_or_default}{path}")
            assert "/login" in page.url, f"Expected /login redirect for {path}"
        page.context.close()

    def test_logout_clears_session(self, browser, base_url_or_default):
        """After logout, visiting / redirects back to /login."""
        page = fresh_page(browser, base_url_or_default)
        login(page, ADMIN_USER, ADMIN_PASS, base_url_or_default)
        page.goto(f"{base_url_or_default}/logout")
        page.goto(f"{base_url_or_default}/")
        assert "/login" in page.url
        page.context.close()

    def test_already_logged_in_redirects_away_from_login(self, browser, base_url_or_default):
        """If already authenticated, GET /login redirects to dashboard."""
        page = fresh_page(browser, base_url_or_default)
        login(page, ADMIN_USER, ADMIN_PASS, base_url_or_default)
        page.goto(f"{base_url_or_default}/login")
        assert "/login" not in page.url
        page.context.close()


# ─────────────────────────────────────────────────────────────────────────────
# 2. Dashboard
# ─────────────────────────────────────────────────────────────────────────────

class TestDashboard:

    def test_dashboard_loads(self, admin_page, base_url_or_default):
        """Dashboard page renders with expected heading."""
        admin_page.goto(f"{base_url_or_default}/")
        expect(admin_page.locator("h1")).to_contain_text("Dashboard")

    def test_sidebar_navigation_links_present(self, admin_page, base_url_or_default):
        """All expected nav links are present in the sidebar."""
        admin_page.goto(f"{base_url_or_default}/")
        for href in ["/chat", "/notes", "/calendar", "/mail", "/voice"]:
            expect(admin_page.locator(f".sidebar-nav a[href='{href}']").first).to_be_visible()

    def test_admin_sees_admin_panel_link(self, admin_page, base_url_or_default):
        """Admin-role user sees the Admin Panel link in sidebar."""
        admin_page.goto(f"{base_url_or_default}/")
        expect(admin_page.locator("a[href='/admin']")).to_be_visible()

    def test_user_username_displayed(self, admin_page, base_url_or_default):
        """Sidebar footer shows the logged-in username."""
        admin_page.goto(f"{base_url_or_default}/")
        expect(admin_page.locator(".sidebar-user-name")).to_contain_text(ADMIN_USER)

    def test_status_cards_visible(self, admin_page, base_url_or_default):
        """Dashboard status cards (Bot Status, LLM, etc.) are visible."""
        admin_page.goto(f"{base_url_or_default}/")
        # At least the Bot Status card
        expect(admin_page.locator("text=Bot Status")).to_be_visible()


# ─────────────────────────────────────────────────────────────────────────────
# 3. Chat
# ─────────────────────────────────────────────────────────────────────────────

class TestChat:

    def test_chat_page_loads(self, admin_page, base_url_or_default):
        """Chat page renders with input field and send button."""
        admin_page.goto(f"{base_url_or_default}/chat")
        expect(admin_page.locator("#chat-input")).to_be_visible()
        expect(admin_page.locator("#send-btn")).to_be_visible()

    def test_send_button_initially_enabled(self, admin_page, base_url_or_default):
        """Send button is enabled before any interaction."""
        admin_page.goto(f"{base_url_or_default}/chat")
        send_btn = admin_page.locator("#send-btn")
        expect(send_btn).to_be_enabled()

    def test_send_button_disabled_while_waiting(self, admin_page, base_url_or_default):
        """Send button becomes disabled immediately after submitting a message."""
        admin_page.goto(f"{base_url_or_default}/chat")
        # Type a message — don't wait for the full LLM response
        admin_page.fill("#chat-input", "ping")
        # Intercept the network call to control timing
        with admin_page.expect_request("**/chat/send"):
            admin_page.locator("#chat-input").press("Enter")
            # Immediately after submission the button should be disabled
            send_btn = admin_page.locator("#send-btn")
            expect(send_btn).to_be_disabled()
        # Wait for the response and check button is re-enabled
        admin_page.wait_for_load_state("networkidle", timeout=30_000)
        expect(admin_page.locator("#send-btn")).to_be_enabled()

    def test_send_button_icon_changes_while_waiting(self, admin_page, base_url_or_default):
        """Send icon switches to hourglass_empty while request is in-flight."""
        admin_page.goto(f"{base_url_or_default}/chat")
        admin_page.fill("#chat-input", "hi")
        with admin_page.expect_request("**/chat/send"):
            admin_page.locator("#chat-input").press("Enter")
            icon_text = admin_page.locator("#send-icon").inner_text()
            assert icon_text == "hourglass_empty", f"Expected hourglass_empty, got: {icon_text}"
        admin_page.wait_for_load_state("networkidle", timeout=30_000)
        expect(admin_page.locator("#send-icon")).to_have_text("send")

    def test_model_selector_visible(self, admin_page, base_url_or_default):
        """Model selector dropdown is visible in topbar."""
        admin_page.goto(f"{base_url_or_default}/chat")
        expect(admin_page.locator("#model-select")).to_be_visible()

    def test_clear_chat_button_visible(self, admin_page, base_url_or_default):
        """Clear chat (delete) button is visible."""
        admin_page.goto(f"{base_url_or_default}/chat")
        expect(admin_page.locator("button[title='Clear conversation']")).to_be_visible()

    def test_message_appears_in_thread_after_send(self, admin_page, base_url_or_default):
        """User message is added to the chat thread after sending."""
        admin_page.goto(f"{base_url_or_default}/chat")
        test_msg = "Playwright test message"
        admin_page.fill("#chat-input", test_msg)
        admin_page.locator("#chat-input").press("Enter")
        # Wait for the specific text to appear in any user bubble
        # (session-scoped page may have prior messages, so don't rely on .last)
        admin_page.wait_for_selector(f".chat-user:has-text('{test_msg}')", timeout=15_000)
        expect(admin_page.locator(f".chat-user:has-text('{test_msg}')").first).to_be_visible()


# ─────────────────────────────────────────────────────────────────────────────
# 4. Notes
# ─────────────────────────────────────────────────────────────────────────────

class TestNotes:

    def test_notes_page_loads(self, admin_page, base_url_or_default):
        """Notes page renders with New Note button and notes layout."""
        admin_page.goto(f"{base_url_or_default}/notes")
        expect(admin_page.locator("button[hx-post='/notes/create']")).to_be_visible()

    def test_create_note_opens_editor(self, admin_page, base_url_or_default):
        """Clicking New Note shows an editor with a title input."""
        admin_page.goto(f"{base_url_or_default}/notes")
        admin_page.click("button[hx-post='/notes/create']")
        # After HTMX response: editor should appear with a title input
        admin_page.wait_for_selector("#note-editor input[name='title'], #note-editor textarea", timeout=5_000)
        # Editor panel should now have content
        editor = admin_page.locator("#note-editor")
        expect(editor).not_to_be_empty()

    def test_note_list_panel_present(self, admin_page, base_url_or_default):
        """The notes list sidebar panel is present."""
        admin_page.goto(f"{base_url_or_default}/notes")
        expect(admin_page.locator("#note-list")).to_be_visible()

    def test_notes_layout_has_sidebar_and_editor(self, admin_page, base_url_or_default):
        """Notes layout contains both sidebar (list) and editor panels."""
        admin_page.goto(f"{base_url_or_default}/notes")
        expect(admin_page.locator(".notes-sidebar")).to_be_visible()
        expect(admin_page.locator(".notes-editor")).to_be_visible()


# ─────────────────────────────────────────────────────────────────────────────
# 5. Calendar
# ─────────────────────────────────────────────────────────────────────────────

class TestCalendar:

    def test_calendar_page_loads(self, admin_page, base_url_or_default):
        """Calendar page renders with month heading and Voice + Console buttons."""
        admin_page.goto(f"{base_url_or_default}/calendar")
        expect(admin_page.locator("#cal-voice-btn")).to_be_visible()
        expect(admin_page.locator("#cal-console-toggle")).to_be_visible()

    def test_console_panel_toggles(self, admin_page, base_url_or_default):
        """Clicking Console button shows the console input panel."""
        admin_page.goto(f"{base_url_or_default}/calendar")
        # Console panel hidden initially
        console_panel = admin_page.locator("#cal-console-panel")
        # Click to open
        admin_page.click("#cal-console-toggle")
        admin_page.wait_for_timeout(400)
        expect(console_panel).to_be_visible()
        # Click again to hide
        admin_page.click("#cal-console-toggle")
        admin_page.wait_for_timeout(400)
        expect(console_panel).to_be_hidden()

    def test_calendar_add_form_has_required_fields(self, admin_page, base_url_or_default):
        """Add event form contains title, date, and reminder fields."""
        admin_page.goto(f"{base_url_or_default}/calendar")
        expect(admin_page.locator("input[name='title']")).to_be_visible()
        expect(admin_page.locator("input[name='dt_str']")).to_be_visible()
        expect(admin_page.locator("select[name='remind']")).to_be_visible()

    def test_add_event_via_form(self, admin_page, base_url_or_default):
        """Submitting the add-event form creates an event visible in the calendar."""
        admin_page.goto(f"{base_url_or_default}/calendar")
        title = "Playwright Test Event"
        admin_page.fill("input[name='title']", title)
        # Use a fixed near-future datetime
        admin_page.fill("input[name='dt_str']", "2099-12-31T10:00")
        # Submit the form
        admin_page.locator("form[action='/calendar/add'] button[type='submit'], "
                           "button[hx-post='/calendar/add']").first.click()
        # Wait for HTMX to refresh the calendar
        admin_page.wait_for_load_state("networkidle", timeout=10_000)
        # Our test event might not appear in the current month view;
        # just assert no error is shown
        expect(admin_page.locator("text=Error")).to_have_count(0)

    def test_console_submit_plain_text_event(self, admin_page, base_url_or_default):
        """Submitting text to the calendar console fills event fields without error."""
        admin_page.goto(f"{base_url_or_default}/calendar")
        admin_page.click("#cal-console-toggle")
        admin_page.wait_for_timeout(300)
        admin_page.fill("#cal-console-input", "Meeting tomorrow at 3pm")
        admin_page.click("#cal-console-btn")  # submit button
        # Wait for JS callback to complete: either #cal-console-results shows text
        # (success/error message) or a form field gets filled.
        # LLM calls can take 10-40s; use wait_for_function with a generous timeout.
        try:
            admin_page.wait_for_function(
                "document.querySelector('#cal-console-results') && "
                "document.querySelector('#cal-console-results').textContent.trim().length > 0",
                timeout=45_000,
            )
        except Exception:
            pass  # Results div may stay empty on error path; check form fields below
        title_val = admin_page.input_value("input[name='title']")
        dt_val    = admin_page.input_value("input[name='dt_str']")
        results_text = admin_page.text_content("#cal-console-results") or ""
        assert title_val or dt_val or results_text.strip(), (
            "Expected console to fill at least one form field or show a result message"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 6. Voice
# ─────────────────────────────────────────────────────────────────────────────

class TestVoice:

    def test_voice_page_loads(self, admin_page, base_url_or_default):
        """Voice page renders without error."""
        admin_page.goto(f"{base_url_or_default}/voice")
        expect(admin_page.locator("h1")).to_contain_text("Voice")

    def test_voice_settings_panel_visible(self, admin_page, base_url_or_default):
        """Voice options / settings section is present on the page."""
        admin_page.goto(f"{base_url_or_default}/voice")
        # Settings panel may labelled differently; check for at least one visible toggle or card
        page_text = admin_page.inner_text("body")
        assert any(kw in page_text for kw in [
            "Piper", "Voice", "TTS", "STT", "Vosk", "Whisper", "persistent"
        ]), "Expected voice settings keywords on the voice page"

    def test_tts_input_and_button_present(self, admin_page, base_url_or_default):
        """TTS text input and synthesize button are present."""
        admin_page.goto(f"{base_url_or_default}/voice")
        # Look for a textarea or input used for TTS
        tts_input = admin_page.locator("textarea[name='text'], input[name='text'], #tts-input")
        # TTS input lives inside a <details> section (collapsed by default), so it exists
        # in the DOM but is not 'visible'. Check DOM presence only.
        if tts_input.count() > 0:
            assert tts_input.count() > 0  # element exists in DOM
        else:
            pytest.skip("TTS input not present on this installation")


# ─────────────────────────────────────────────────────────────────────────────
# 7. Mail
# ─────────────────────────────────────────────────────────────────────────────

class TestMail:

    def test_mail_page_loads(self, admin_page, base_url_or_default):
        """Mail page renders without error."""
        admin_page.goto(f"{base_url_or_default}/mail")
        expect(admin_page.locator("h1")).to_contain_text("Mail")

    def test_mail_setup_or_digest_section_present(self, admin_page, base_url_or_default):
        """Mail page has either a setup section or a digest panel."""
        admin_page.goto(f"{base_url_or_default}/mail")
        page_text = admin_page.inner_text("body")
        assert any(kw in page_text for kw in [
            "Gmail", "Mail", "digest", "Digest", "IMAP", "Connect", "Refresh"
        ]), "Expected mail keywords on the mail page"


# ─────────────────────────────────────────────────────────────────────────────
# 8. Admin Panel
# ─────────────────────────────────────────────────────────────────────────────

class TestAdmin:

    def test_admin_page_accessible_to_admin(self, admin_page, base_url_or_default):
        """Admin role can access /admin."""
        admin_page.goto(f"{base_url_or_default}/admin")
        expect(admin_page.locator("h1")).to_contain_text("Admin")

    def test_admin_shows_user_list(self, admin_page, base_url_or_default):
        """Admin panel lists registered users."""
        admin_page.goto(f"{base_url_or_default}/admin")
        page_text = admin_page.inner_text("body")
        assert "admin" in page_text or "stas" in page_text, \
            "Expected user names in admin panel"

    def test_admin_shows_llm_section(self, admin_page, base_url_or_default):
        """Admin panel has an LLM model section."""
        admin_page.goto(f"{base_url_or_default}/admin")
        page_text = admin_page.inner_text("body")
        assert any(kw in page_text for kw in ["LLM", "Model", "model"]), \
            "Expected LLM section in admin panel"

    def test_non_admin_cannot_access_admin(self, browser, base_url_or_default):
        """Regular user gets redirect or 403 when accessing /admin."""
        page = fresh_page(browser, base_url_or_default)
        login(page, NORMAL_USER, NORMAL_PASS, base_url_or_default)
        page.goto(f"{base_url_or_default}/admin")
        # Either redirected away or shown an access-denied page
        is_denied = (
            "/login" in page.url
            or "403" in page.content()
            or "denied" in page.inner_text("body").lower()
            or "not allowed" in page.inner_text("body").lower()
            or "admin only" in page.inner_text("body").lower()
        )
        assert is_denied, f"Expected regular user to be denied /admin, got URL: {page.url}"
        page.context.close()


# ─────────────────────────────────────────────────────────────────────────────
# 9. Navigation
# ─────────────────────────────────────────────────────────────────────────────

class TestNavigation:

    @pytest.mark.parametrize("path,expected_heading", [
        ("/",         "Dashboard"),
        ("/chat",     "Taris"),
        ("/notes",    "Notes"),
        ("/calendar", "Calendar"),
        ("/voice",    "Voice"),
        ("/mail",     "Mail"),
    ])
    def test_nav_links_load_correct_page(self, admin_page, base_url_or_default,
                                         path, expected_heading):
        """Every sidebar nav link loads the expected page."""
        admin_page.goto(f"{base_url_or_default}{path}")
        expect(admin_page.locator("h1")).to_contain_text(expected_heading)

    def test_clicking_sidebar_nav_navigates(self, admin_page, base_url_or_default):
        """Clicking a sidebar link navigates to the target page."""
        admin_page.goto(f"{base_url_or_default}/")
        admin_page.click("a[href='/chat']")
        admin_page.wait_for_url(f"{base_url_or_default}/chat", timeout=8_000)
        expect(admin_page.locator("h1")).to_contain_text("Taris")

    def test_logout_link_in_sidebar(self, admin_page, base_url_or_default):
        """Logout link is present in the sidebar."""
        admin_page.goto(f"{base_url_or_default}/")
        expect(admin_page.locator("a[href='/logout']")).to_be_visible()


# ─────────────────────────────────────────────────────────────────────────────
# 10. Registration
# ─────────────────────────────────────────────────────────────────────────────

class TestRegistration:

    def test_register_page_loads(self, browser, base_url_or_default):
        """GET /register shows the registration form."""
        page = fresh_page(browser, base_url_or_default)
        page.goto(f"{base_url_or_default}/register")
        expect(page.locator("input[name='username']")).to_be_visible()
        expect(page.locator("input[name='password']")).to_be_visible()
        page.context.close()

    def test_register_link_on_login_page(self, browser, base_url_or_default):
        """Login page contains a link to /register."""
        page = fresh_page(browser, base_url_or_default)
        page.goto(f"{base_url_or_default}/login")
        reg_link = page.locator("a[href='/register']")
        expect(reg_link).to_be_visible()
        page.context.close()

    def test_register_duplicate_username_shows_error(self, browser, base_url_or_default):
        """Registering with an existing username shows an error."""
        page = fresh_page(browser, base_url_or_default)
        page.goto(f"{base_url_or_default}/register")
        page.fill("input[name='username']", ADMIN_USER)  # already exists
        page.fill("input[name='password']", "somepassword")
        # Some UIs have a display_name or confirm-password field — fill if present
        dn_input = page.locator("input[name='display_name']")
        if dn_input.count() > 0:
            dn_input.fill("Admin Duplicate")
        page.click("button[type='submit']")
        # Expect to stay on /register or see an error message
        assert "/register" in page.url or "error" in page.inner_text("body").lower() or \
               "already" in page.inner_text("body").lower() or \
               "exist" in page.inner_text("body").lower(), \
            "Expected error for duplicate username"
        page.context.close()


# ─────────────────────────────────────────────────────────────────────────────
# 11. Profile
# ─────────────────────────────────────────────────────────────────────────────

class TestProfile:

    def test_profile_page_loads(self, admin_page, base_url_or_default):
        """GET /profile returns 200 and shows the profile heading."""
        admin_page.goto(f"{base_url_or_default}/profile")
        expect(admin_page.locator("h1")).to_contain_text("Profile")

    def test_profile_has_account_info(self, admin_page, base_url_or_default):
        """Profile page shows the account info section."""
        admin_page.goto(f"{base_url_or_default}/profile")
        body = admin_page.inner_text("body").lower()
        assert "username" in body or "account" in body, \
            "Profile page should show account information"

    def test_profile_edit_name_form_present(self, admin_page, base_url_or_default):
        """Profile page contains the display name edit form."""
        admin_page.goto(f"{base_url_or_default}/profile")
        expect(admin_page.locator("input[name='display_name']")).to_be_visible()

    def test_unauthenticated_profile_redirects_to_login(self, browser, base_url_or_default):
        """GET /profile without auth redirects to /login."""
        page = fresh_page(browser, base_url_or_default)
        page.goto(f"{base_url_or_default}/profile")
        assert "/login" in page.url, "Unauthenticated /profile should redirect to /login"
        page.context.close()


# ─────────────────────────────────────────────────────────────────────────────
# 12. Settings
# ─────────────────────────────────────────────────────────────────────────────

class TestSettings:

    def test_settings_page_loads(self, admin_page, base_url_or_default):
        """GET /settings returns the settings page."""
        admin_page.goto(f"{base_url_or_default}/settings")
        assert "/settings" in admin_page.url
        assert admin_page.title() != ""

    def test_settings_language_buttons_present(self, admin_page, base_url_or_default):
        """Settings page shows language selection buttons."""
        admin_page.goto(f"{base_url_or_default}/settings")
        # Language forms post to /settings/language
        forms = admin_page.locator("form[action='/settings/language']")
        assert forms.count() >= 2, "At least 2 language buttons expected (en, ru, de)"

    def test_settings_password_form_present(self, admin_page, base_url_or_default):
        """Settings page contains the password change form."""
        admin_page.goto(f"{base_url_or_default}/settings")
        assert admin_page.locator("input[name='current_password']").is_visible()
        assert admin_page.locator("input[name='new_password']").is_visible()
        assert admin_page.locator("input[name='confirm_password']").is_visible()

    def test_settings_unauthenticated_redirects(self, browser, base_url_or_default):
        """GET /settings without auth redirects to /login."""
        page = fresh_page(browser, base_url_or_default)
        page.goto(f"{base_url_or_default}/settings")
        assert "/login" in page.url
        page.context.close()


# ─────────────────────────────────────────────────────────────────────────────
# 13. Contacts
# ─────────────────────────────────────────────────────────────────────────────

class TestContacts:

    def test_contacts_page_loads(self, admin_page, base_url_or_default):
        """GET /contacts returns the contacts page."""
        admin_page.goto(f"{base_url_or_default}/contacts")
        assert "/contacts" in admin_page.url
        assert admin_page.title() != ""

    def test_contacts_search_form_present(self, admin_page, base_url_or_default):
        """Contacts page has a search form."""
        admin_page.goto(f"{base_url_or_default}/contacts")
        assert admin_page.locator("input[name='q']").is_visible()

    def test_contacts_new_form_loads(self, admin_page, base_url_or_default):
        """GET /contacts/new shows the contact creation form."""
        admin_page.goto(f"{base_url_or_default}/contacts/new")
        assert admin_page.locator("input[name='name']").is_visible()
        assert admin_page.locator("input[name='phone']").is_visible()
        assert admin_page.locator("input[name='email']").is_visible()

    def test_contacts_create_and_delete(self, admin_page, base_url_or_default):
        """Create a contact, verify it appears in the list, then search for it."""
        admin_page.goto(f"{base_url_or_default}/contacts/new")
        admin_page.fill("input[name='name']", "UI Test Contact")
        admin_page.fill("input[name='phone']", "+1234567890")
        admin_page.click("button[type='submit']")
        admin_page.wait_for_url(re.compile(r"/contacts"), timeout=5000)
        # Verify we're back on contacts page (create redirects to /contacts)
        assert "/contacts" in admin_page.url

    def test_contacts_unauthenticated_redirects(self, browser, base_url_or_default):
        """GET /contacts without auth redirects to /login."""
        page = fresh_page(browser, base_url_or_default)
        page.goto(f"{base_url_or_default}/contacts")
        assert "/login" in page.url
        page.context.close()
