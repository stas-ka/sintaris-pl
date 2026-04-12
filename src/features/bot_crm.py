"""
bot_crm.py — CRM business logic and Telegram/Web handlers.

Provides contact management, task tracking, campaign management,
and AI-powered features (tagging, audience matching).
"""

import json
import logging
from typing import Any

from core.bot_config import CRM_ENABLED, CRM_PG_DSN
from core import store_crm as crm

log = logging.getLogger("taris.crm")


def is_available() -> bool:
    """Check if CRM module is available and configured."""
    return CRM_ENABLED and bool(CRM_PG_DSN)


# ─────────────────────────────────────────────────────────────────────────────
# Contact management
# ─────────────────────────────────────────────────────────────────────────────

def add_contact(first_name: str, last_name: str,
                owner_user_id: int = 0, **kwargs) -> dict:
    """Add a new contact. Returns {ok, id} or {ok, error}."""
    if not is_available():
        return {"ok": False, "error": "CRM not configured"}
    try:
        cid = crm.create_contact(first_name, last_name,
                                 owner_user_id=owner_user_id, **kwargs)
        log.info("[CRM] contact created: %s %s (id=%d)", first_name, last_name, cid)
        return {"ok": True, "id": cid}
    except Exception as e:
        log.error("[CRM] add_contact error: %s", e)
        return {"ok": False, "error": str(e)}


def get_contact(contact_id: int) -> dict | None:
    """Get contact by ID."""
    if not is_available():
        return None
    return crm.get_contact(contact_id)


def search(query: str, limit: int = 20) -> list[dict]:
    """Search contacts by name, email, phone, etc."""
    if not is_available():
        return []
    return crm.search_contacts(query, limit)


def list_contacts(status: str = "active", limit: int = 50) -> list[dict]:
    """List contacts with given status."""
    if not is_available():
        return []
    return crm.list_contacts(status, limit)


def delete_contact(contact_id: int) -> bool:
    """Delete a contact."""
    if not is_available():
        return False
    return crm.delete_contact(contact_id)


def update_contact(contact_id: int, **fields) -> bool:
    """Update contact fields."""
    if not is_available():
        return False
    return crm.update_contact(contact_id, **fields)


# ─────────────────────────────────────────────────────────────────────────────
# AI-powered features
# ─────────────────────────────────────────────────────────────────────────────

def ai_tag_contact(contact_id: int) -> dict:
    """Use LLM to generate tags, segment, and summary for a contact."""
    if not is_available():
        return {"ok": False, "error": "CRM not available"}
    contact = crm.get_contact(contact_id)
    if not contact:
        return {"ok": False, "error": "Contact not found"}

    from core.bot_llm import ask_llm
    prompt = (
        f"Analyze this CRM contact and return JSON with keys: "
        f"tags (list of 3-5 keywords), segment (one of: corporate, individual, partner, lead), "
        f"summary (one sentence description).\n\n"
        f"Contact: {contact['first_name']} {contact['last_name']}\n"
        f"Email: {contact.get('email', '')}\n"
        f"Phone: {contact.get('phone', '')}\n"
        f"City: {contact.get('city', '')}\n"
        f"Extra: {contact.get('extra_info', '')}\n\n"
        f"Return ONLY valid JSON, no explanation."
    )
    raw = ask_llm(prompt, timeout=30, use_case="system")
    if not raw:
        return {"ok": False, "error": "LLM returned empty response"}
    try:
        # Strip markdown code fences if present
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
            if clean.endswith("```"):
                clean = clean[:-3]
        data = json.loads(clean)
        tags = data.get("tags", [])
        segment = data.get("segment", "")
        summary = data.get("summary", "")
        crm.update_contact(contact_id, tags=tags, segment=segment, summary=summary)
        return {"ok": True, "tags": tags, "segment": segment, "summary": summary}
    except (json.JSONDecodeError, KeyError) as e:
        log.warning("[CRM] AI tagging parse error: %s", e)
        return {"ok": False, "error": f"LLM response parse error: {e}"}


def ai_match_contacts(audience_description: str, limit: int = 20) -> list[dict]:
    """Use LLM to score contacts against an audience description.

    Returns contacts with ai_score and ai_reason.
    """
    if not is_available():
        return []
    contacts = crm.list_contacts("active", limit=200)
    if not contacts:
        return []

    from core.bot_llm import ask_llm
    contacts_text = "\n".join(
        f"ID={c['id']}: {c['first_name']} {c['last_name']} | "
        f"{c.get('segment', '')} | {c.get('summary', '')} | "
        f"tags={c.get('tags', [])}"
        for c in contacts
    )
    prompt = (
        f"You are a CRM analyst. Score each contact 0.0-1.0 for relevance to "
        f"this audience: \"{audience_description}\"\n\n"
        f"Contacts:\n{contacts_text}\n\n"
        f"Return JSON array of objects with keys: id, score, reason. "
        f"Only include contacts with score >= 0.3. Sort by score descending. "
        f"Max {limit} results. Return ONLY valid JSON array."
    )
    raw = ask_llm(prompt, timeout=60, use_case="system")
    if not raw:
        return []
    try:
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
            if clean.endswith("```"):
                clean = clean[:-3]
        matches = json.loads(clean)
        result = []
        contact_map = {c["id"]: c for c in contacts}
        for m in matches[:limit]:
            cid = m.get("id")
            if cid in contact_map:
                entry = dict(contact_map[cid])
                entry["ai_score"] = m.get("score", 0.0)
                entry["ai_reason"] = m.get("reason", "")
                result.append(entry)
        return result
    except (json.JSONDecodeError, KeyError) as e:
        log.warning("[CRM] AI match parse error: %s", e)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Task management
# ─────────────────────────────────────────────────────────────────────────────

def add_task(title: str, *, contact_id: int | None = None,
             description: str = "", due_date: str = "",
             priority: str = "medium",
             owner_user_id: int = 0) -> dict:
    if not is_available():
        return {"ok": False, "error": "CRM not available"}
    try:
        tid = crm.create_task(title, contact_id=contact_id,
                              description=description, due_date=due_date,
                              priority=priority, owner_user_id=owner_user_id)
        return {"ok": True, "id": tid}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def list_tasks(status: str = "active") -> list[dict]:
    if not is_available():
        return []
    return crm.list_tasks(status)


def complete_task(task_id: int) -> bool:
    if not is_available():
        return False
    return crm.complete_task(task_id)


# ─────────────────────────────────────────────────────────────────────────────
# Campaign management
# ─────────────────────────────────────────────────────────────────────────────

def create_campaign(title: str, target_audience: str = "",
                    description: str = "", message_template: str = "",
                    keywords: list[str] | None = None) -> dict:
    if not is_available():
        return {"ok": False, "error": "CRM not available"}
    try:
        cid = crm.create_campaign(title, description=description,
                                  target_audience=target_audience,
                                  keywords=keywords,
                                  message_template=message_template)
        return {"ok": True, "id": cid}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def match_campaign_contacts(campaign_id: int) -> list[dict]:
    """AI-match contacts for a campaign based on its target_audience."""
    campaign = crm.get_campaign(campaign_id)
    if not campaign:
        return []
    matched = ai_match_contacts(campaign.get("target_audience", ""), limit=50)
    for m in matched:
        crm.add_campaign_contact(campaign_id, m["id"],
                                 ai_score=m.get("ai_score", 0),
                                 ai_reason=m.get("ai_reason", ""))
    return matched


def get_campaign_contacts(campaign_id: int) -> list[dict]:
    if not is_available():
        return []
    return crm.list_campaign_contacts(campaign_id)


def approve_campaign(campaign_id: int) -> bool:
    """Mark campaign as approved (ready to send)."""
    return crm.update_campaign_status(campaign_id, "approved")


def get_stats() -> dict:
    """Get CRM statistics summary."""
    if not is_available():
        return {"contacts": 0, "active_tasks": 0, "campaigns": 0, "interactions": 0}
    try:
        return crm.get_stats()
    except Exception as e:
        log.error("[CRM] stats error: %s", e)
        return {"contacts": 0, "active_tasks": 0, "campaigns": 0, "interactions": 0}


# ─────────────────────────────────────────────────────────────────────────────
# LLM Intent Classification for CRM commands
# ─────────────────────────────────────────────────────────────────────────────

CRM_INTENTS = {"add_contact", "search", "list", "campaign", "task", "stats", "unknown"}


def classify_intent(text: str) -> dict:
    """Classify user text into CRM intent.

    Returns {intent: str, params: dict} where intent is one of CRM_INTENTS.
    """
    from core.bot_llm import ask_llm
    prompt = (
        f"Classify this CRM command into one of: add_contact, search, list, "
        f"campaign, task, stats.\n"
        f"Also extract parameters if present.\n"
        f"User: \"{text}\"\n\n"
        f"Return JSON: {{\"intent\": \"...\", \"params\": {{...}}}}\n"
        f"Examples:\n"
        f"  \"Добавь контакт Иванов Иван\" → {{\"intent\": \"add_contact\", \"params\": {{\"first_name\": \"Иван\", \"last_name\": \"Иванов\"}}}}\n"
        f"  \"Найди клиентов из Москвы\" → {{\"intent\": \"search\", \"params\": {{\"query\": \"Москва\"}}}}\n"
        f"  \"Создай кампанию для предпринимателей\" → {{\"intent\": \"campaign\", \"params\": {{\"target\": \"предприниматели\"}}}}\n"
        f"Return ONLY valid JSON."
    )
    raw = ask_llm(prompt, timeout=20, use_case="system")
    if not raw:
        return {"intent": "unknown", "params": {}}
    try:
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
            if clean.endswith("```"):
                clean = clean[:-3]
        data = json.loads(clean)
        intent = data.get("intent", "unknown")
        if intent not in CRM_INTENTS:
            intent = "unknown"
        return {"intent": intent, "params": data.get("params", {})}
    except (json.JSONDecodeError, KeyError):
        return {"intent": "unknown", "params": {}}
