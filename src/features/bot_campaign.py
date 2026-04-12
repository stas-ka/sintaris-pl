"""
bot_campaign.py — Campaign Agent: AI-assisted client email campaign via N8N.

Flow:
  1. User starts campaign from Agents menu
  2. Enters topic + optional filters
  3. Taris calls N8N "taris-campaign-select" webhook (synchronous)
  4. N8N reads Google Sheets clients, GPT-4o-mini selects audience + generates template
  5. User reviews preview, optionally edits template
  6. User confirms → Taris calls N8N "taris-campaign-send" webhook (synchronous)
  7. N8N sends Gmail, logs to Google Sheets "Статус рассылок"
  8. User gets sent count + sheet link
"""

import logging
import threading
import uuid
from typing import Any

from features.bot_n8n import call_webhook

from core.bot_config import (
    N8N_CAMPAIGN_SELECT_WH,
    N8N_CAMPAIGN_SEND_WH,
    CAMPAIGN_SHEET_ID,
    N8N_CAMPAIGN_TIMEOUT,
    CAMPAIGN_DEMO_MODE,
)

log = logging.getLogger("taris.campaign")

# ─────────────────────────────────────────────────────────────────────────────
# State — keyed by chat_id
# Steps: idle → topic_input → filter_input → selecting → preview → editing → sending
# ─────────────────────────────────────────────────────────────────────────────
_campaigns: dict[int, dict] = {}

SHEET_STATUS_URL = (
    f"https://docs.google.com/spreadsheets/d/{CAMPAIGN_SHEET_ID}"
    "/edit#gid=0"
)

# ─────────────────────────────────────────────────────────────────────────────
# Public API: state accessors
# ─────────────────────────────────────────────────────────────────────────────

def is_active(chat_id: int) -> bool:
    """Return True if chat_id is currently in a campaign flow."""
    return chat_id in _campaigns


def get_step(chat_id: int) -> str:
    """Return current step for chat_id, or 'idle'."""
    return _campaigns.get(chat_id, {}).get("step", "idle")


def cancel(chat_id: int) -> None:
    """Cancel and clean up any active campaign for chat_id."""
    _campaigns.pop(chat_id, None)


def is_configured() -> bool:
    """Return True if N8N campaign webhooks are configured."""
    return bool(N8N_CAMPAIGN_SELECT_WH and N8N_CAMPAIGN_SEND_WH)


# ─────────────────────────────────────────────────────────────────────────────
# N8N helpers
# ─────────────────────────────────────────────────────────────────────────────

def _truncate(text: str, max_len: int = 200) -> str:
    return text[:max_len] + "…" if len(text) > max_len else text


# Maps N8N step names (returned in {step: "..."} error responses) to i18n keys
_STEP_KEY_MAP = {
    # Demo path
    "Demo Clients":      "campaign_error_input",
    # Google Sheets nodes
    "GS Read Clients":   "campaign_error_input",
    "GS Read Templates": "campaign_error_workflow",
    "GS Append Status":  "campaign_error_workflow",
    "Merge Template":    "campaign_error_workflow",
    # Processing nodes
    "Prepare Prompt":    "campaign_error_input",
    "OpenAI Select":     "campaign_error_openai",
    "Parse Response":    "campaign_error_workflow",
    "Expand Clients":    "campaign_error_input",
    # Send nodes
    "Send Gmail":        "campaign_error_email",
    "Prepare Sheet Row": "campaign_error_workflow",
    "Build Sheet Row":   "campaign_error_workflow",
    "Summary":           "campaign_error_workflow",
}


def _user_friendly_error(step: str, detail: str, _t, chat_id: int) -> str:
    """Return a localised, user-readable error string for the given N8N step."""
    key = _STEP_KEY_MAP.get(step, "campaign_error_workflow")
    return _t(chat_id, key, step=step, detail=_truncate(detail))


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — Start campaign
# ─────────────────────────────────────────────────────────────────────────────

def start_campaign(chat_id: int, bot, _t) -> None:
    """Begin campaign flow: ask for topic."""
    _campaigns[chat_id] = {
        "step": "topic_input",
        "session_id": str(uuid.uuid4()),
        "topic": "",
        "filters": "",
        "clients": [],
        "template": "",
    }
    bot.send_message(
        chat_id,
        _t(chat_id, "campaign_enter_topic"),
        parse_mode="Markdown",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — Receive topic
# ─────────────────────────────────────────────────────────────────────────────

def on_topic(chat_id: int, text: str, bot, _t) -> None:
    """Store topic, ask for optional filters."""
    state = _campaigns.get(chat_id)
    if not state or state["step"] != "topic_input":
        return
    state["topic"] = text.strip()
    state["step"] = "filter_input"
    bot.send_message(
        chat_id,
        _t(chat_id, "campaign_enter_filters"),
        parse_mode="Markdown",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — Receive filters (or skip) → trigger N8N select
# ─────────────────────────────────────────────────────────────────────────────

def on_filters(chat_id: int, text: str, bot, _t) -> None:
    """Store filters, trigger N8N selection in background thread."""
    state = _campaigns.get(chat_id)
    if not state or state["step"] != "filter_input":
        return
    filters = text.strip()
    if filters.lower() in ("-", "нет", "no", "skip", ""):
        filters = ""
    state["filters"] = filters
    state["step"] = "selecting"
    bot.send_message(chat_id, _t(chat_id, "campaign_selecting"), parse_mode="Markdown")
    threading.Thread(
        target=_run_selection, args=(chat_id, bot, _t), daemon=True
    ).start()


def _run_selection(chat_id: int, bot, _t) -> None:
    """Call N8N select webhook synchronously; deliver preview to user."""
    state = _campaigns.get(chat_id)
    if not state:
        return

    payload = {
        "session_id": state["session_id"],
        "topic": state["topic"],
        "filters": state["filters"],
        "sheet_id": CAMPAIGN_SHEET_ID,
        "demo_mode": CAMPAIGN_DEMO_MODE,
    }

    result = call_webhook(N8N_CAMPAIGN_SELECT_WH, payload, timeout=N8N_CAMPAIGN_TIMEOUT)

    # call_webhook returns {"error": "...", "status_code": N} on transport failure
    # N8N returns {"error": "...", "step": "..."} on workflow error
    if "error" in result:
        step = result.get("step", "unknown")
        detail = result.get("error", "Unknown error")
        log.error("[Campaign] select failed step=%s detail=%s", step, detail)
        _campaigns.pop(chat_id, None)
        bot.send_message(
            chat_id,
            _user_friendly_error(step, detail, _t, chat_id),
        )
        return

    clients = result.get("clients", [])
    template = result.get("template", "")

    if not clients:
        _campaigns.pop(chat_id, None)
        bot.send_message(chat_id, _t(chat_id, "campaign_no_clients"))
        return

    state["clients"] = clients
    state["template"] = template
    state["step"] = "preview"

    _send_preview(chat_id, bot, _t)


# ─────────────────────────────────────────────────────────────────────────────
# Preview UI
# ─────────────────────────────────────────────────────────────────────────────

def _send_preview(chat_id: int, bot, _t) -> None:
    """Send the campaign preview with approve/edit/cancel buttons."""
    try:
        from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    except ImportError:
        from telebot import types
        InlineKeyboardMarkup = types.InlineKeyboardMarkup
        InlineKeyboardButton = types.InlineKeyboardButton

    state = _campaigns[chat_id]
    clients = state["clients"]
    template = state["template"]

    # Build client summary (first 5 names)
    names = [c.get("name", c.get("Имя", "?")) for c in clients[:5]]
    names_str = ", ".join(names)
    if len(clients) > 5:
        names_str += f", … (+{len(clients) - 5})"

    # Truncate template preview
    tpl_preview = template[:300] + ("…" if len(template) > 300 else "")

    text = _t(
        chat_id,
        "campaign_preview",
        count=len(clients),
        names=names_str,
        template=tpl_preview,
    )

    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(_t(chat_id, "campaign_btn_send"), callback_data="campaign_confirm_send"),
        InlineKeyboardButton(_t(chat_id, "campaign_btn_edit"), callback_data="campaign_edit_template"),
    )
    kb.add(
        InlineKeyboardButton(_t(chat_id, "campaign_btn_cancel"), callback_data="campaign_cancel"),
    )

    bot.send_message(chat_id, text, reply_markup=kb, parse_mode="Markdown")


# ─────────────────────────────────────────────────────────────────────────────
# Template editing
# ─────────────────────────────────────────────────────────────────────────────

def start_template_edit(chat_id: int, bot, _t) -> None:
    """Ask user to send new template text."""
    state = _campaigns.get(chat_id)
    if not state or state["step"] != "preview":
        return
    state["step"] = "editing"
    current = state.get("template", "")
    bot.send_message(
        chat_id,
        _t(chat_id, "campaign_edit_prompt", template=current),
        parse_mode="Markdown",
    )


def on_template_edit(chat_id: int, text: str, bot, _t) -> None:
    """Save edited template, return to preview."""
    state = _campaigns.get(chat_id)
    if not state or state["step"] != "editing":
        return
    state["template"] = text.strip()
    state["step"] = "preview"
    bot.send_message(chat_id, _t(chat_id, "campaign_template_saved"))
    _send_preview(chat_id, bot, _t)


# ─────────────────────────────────────────────────────────────────────────────
# Step 4 — Confirm send → trigger N8N send
# ─────────────────────────────────────────────────────────────────────────────

def confirm_send(chat_id: int, bot, _t) -> None:
    """User confirmed: trigger N8N send workflow in background."""
    state = _campaigns.get(chat_id)
    if not state or state["step"] not in ("preview", "editing"):
        return
    state["step"] = "sending"
    bot.send_message(chat_id, _t(chat_id, "campaign_sending"), parse_mode="Markdown")
    threading.Thread(
        target=_run_send, args=(chat_id, bot, _t), daemon=True
    ).start()


def _run_send(chat_id: int, bot, _t) -> None:
    """Call N8N send webhook; notify user of result."""
    state = _campaigns.pop(chat_id, None)
    if not state:
        return

    payload = {
        "session_id": state["session_id"],
        "topic": state["topic"],
        "clients": state["clients"],
        "template": state["template"],
        "sheet_id": CAMPAIGN_SHEET_ID,
        "demo_mode": CAMPAIGN_DEMO_MODE,
    }

    result = call_webhook(N8N_CAMPAIGN_SEND_WH, payload, timeout=N8N_CAMPAIGN_TIMEOUT)

    if "error" in result:
        step = result.get("step", "unknown")
        detail = result.get("error", "Unknown error")
        failed_emails = result.get("failed_emails", "")
        log.error("[Campaign] send failed step=%s detail=%s", step, detail)
        bot.send_message(
            chat_id,
            _user_friendly_error(step, detail, _t, chat_id),
        )
        return

    sent = result.get("sent_count", 0)
    failed = result.get("failed_count", 0)
    total = result.get("total_count", len(state["clients"]))
    sheet_url = result.get("sheet_url", SHEET_STATUS_URL)
    failed_emails = result.get("failed_emails", "")

    if failed > 0:
        log.warning(
            "[Campaign] partial send: %d/%d sent, failed: %s", sent, total, failed_emails
        )
        bot.send_message(
            chat_id,
            _t(chat_id, "campaign_partial_send",
               sent=sent, total=total, failed_emails=failed_emails, url=sheet_url),
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
    else:
        bot.send_message(
            chat_id,
            _t(chat_id, "campaign_done", sent=sent, url=sheet_url),
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Message dispatcher — call from handle_message for text input
# ─────────────────────────────────────────────────────────────────────────────

def handle_message(chat_id: int, text: str, bot, _t) -> bool:
    """Handle text input for any active campaign step.

    Returns True if the message was consumed by the campaign flow.
    """
    state = _campaigns.get(chat_id)
    if not state:
        return False
    step = state.get("step")
    if step == "topic_input":
        on_topic(chat_id, text, bot, _t)
        return True
    if step == "filter_input":
        on_filters(chat_id, text, bot, _t)
        return True
    if step == "editing":
        on_template_edit(chat_id, text, bot, _t)
        return True
    return False
