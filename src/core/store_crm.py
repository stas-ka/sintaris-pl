"""
store_crm.py — CRM data access layer (PostgreSQL).

Manages crm_contacts, crm_interactions, crm_tasks, crm_campaigns,
crm_campaign_contacts on the VPS PostgreSQL database.
"""

import logging
from contextlib import contextmanager
from datetime import datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row

from core.bot_config import CRM_PG_DSN, CRM_ENABLED

log = logging.getLogger("taris.crm_store")

_pool = None


def _get_pool():
    global _pool
    if _pool is None:
        if not CRM_PG_DSN:
            raise RuntimeError("CRM_PG_DSN not configured")
        from psycopg_pool import ConnectionPool
        _pool = ConnectionPool(CRM_PG_DSN, min_size=1, max_size=3,
                               kwargs={"row_factory": dict_row})
        log.info("[CRM] connection pool created")
    return _pool


@contextmanager
def _conn():
    pool = _get_pool()
    with pool.connection() as c:
        yield c


def is_available() -> bool:
    """Check if CRM store is configured and reachable."""
    if not CRM_ENABLED or not CRM_PG_DSN:
        return False
    try:
        with _conn() as c:
            c.execute("SELECT 1")
        return True
    except Exception as e:
        log.warning("[CRM] connection check failed: %s", e)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Contacts
# ─────────────────────────────────────────────────────────────────────────────

def create_contact(first_name: str, last_name: str, *,
                   phone: str = "", email: str = "", telegram: str = "",
                   city: str = "", tags: list[str] | None = None,
                   segment: str = "", summary: str = "",
                   lead_source: str = "", extra_info: str = "",
                   owner_user_id: int = 0) -> int:
    """Insert a new contact. Returns the new contact ID."""
    with _conn() as c:
        row = c.execute(
            """INSERT INTO crm_contacts
               (first_name, last_name, phone, email, telegram, city,
                tags, segment, summary, lead_source, extra_info, owner_user_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (first_name, last_name, phone, email, telegram, city,
             tags or [], segment, summary, lead_source, extra_info,
             owner_user_id)
        ).fetchone()
        return row["id"]


def get_contact(contact_id: int) -> dict | None:
    with _conn() as c:
        return c.execute(
            "SELECT * FROM crm_contacts WHERE id = %s", (contact_id,)
        ).fetchone()


def update_contact(contact_id: int, **fields) -> bool:
    """Update contact fields. Returns True if updated."""
    allowed = {"first_name", "last_name", "phone", "email", "telegram",
               "city", "tags", "segment", "summary", "lead_source",
               "extra_info", "status", "owner_user_id"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    updates["updated_at"] = datetime.utcnow()
    sets = ", ".join(f"{k} = %s" for k in updates)
    with _conn() as c:
        c.execute(f"UPDATE crm_contacts SET {sets} WHERE id = %s",
                  (*updates.values(), contact_id))
        return c.rowcount > 0


def delete_contact(contact_id: int) -> bool:
    with _conn() as c:
        c.execute("DELETE FROM crm_contacts WHERE id = %s", (contact_id,))
        return c.rowcount > 0


def list_contacts(status: str = "active", limit: int = 50,
                  offset: int = 0) -> list[dict]:
    with _conn() as c:
        return c.execute(
            """SELECT * FROM crm_contacts
               WHERE status = %s
               ORDER BY updated_at DESC LIMIT %s OFFSET %s""",
            (status, limit, offset)
        ).fetchall()


def search_contacts(query: str, limit: int = 20) -> list[dict]:
    """Full-text search across name, email, phone, tags, summary."""
    pattern = f"%{query}%"
    with _conn() as c:
        return c.execute(
            """SELECT * FROM crm_contacts
               WHERE first_name ILIKE %s OR last_name ILIKE %s
                  OR email ILIKE %s OR phone ILIKE %s
                  OR telegram ILIKE %s OR summary ILIKE %s
                  OR extra_info ILIKE %s
               ORDER BY updated_at DESC LIMIT %s""",
            (pattern, pattern, pattern, pattern, pattern, pattern,
             pattern, limit)
        ).fetchall()


def count_contacts(status: str | None = None) -> int:
    with _conn() as c:
        if status:
            return c.execute(
                "SELECT COUNT(*) AS cnt FROM crm_contacts WHERE status = %s",
                (status,)
            ).fetchone()["cnt"]
        return c.execute(
            "SELECT COUNT(*) AS cnt FROM crm_contacts"
        ).fetchone()["cnt"]


# ─────────────────────────────────────────────────────────────────────────────
# Interactions
# ─────────────────────────────────────────────────────────────────────────────

def add_interaction(contact_id: int, type_: str, content: str = "",
                    result: str = "", author_user_id: int = 0) -> int:
    with _conn() as c:
        row = c.execute(
            """INSERT INTO crm_interactions (contact_id, type, content, result, author_user_id)
               VALUES (%s, %s, %s, %s, %s) RETURNING id""",
            (contact_id, type_, content, result, author_user_id)
        ).fetchone()
        return row["id"]


def list_interactions(contact_id: int, limit: int = 20) -> list[dict]:
    with _conn() as c:
        return c.execute(
            """SELECT * FROM crm_interactions
               WHERE contact_id = %s ORDER BY created_at DESC LIMIT %s""",
            (contact_id, limit)
        ).fetchall()


# ─────────────────────────────────────────────────────────────────────────────
# Tasks
# ─────────────────────────────────────────────────────────────────────────────

def create_task(title: str, *, contact_id: int | None = None,
                description: str = "", due_date: str = "",
                priority: str = "medium",
                owner_user_id: int = 0) -> int:
    dd = due_date or None
    with _conn() as c:
        row = c.execute(
            """INSERT INTO crm_tasks (contact_id, title, description, due_date, priority, owner_user_id)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
            (contact_id, title, description, dd, priority, owner_user_id)
        ).fetchone()
        return row["id"]


def list_tasks(status: str = "active", limit: int = 50) -> list[dict]:
    with _conn() as c:
        return c.execute(
            """SELECT t.*, c.first_name, c.last_name
               FROM crm_tasks t
               LEFT JOIN crm_contacts c ON t.contact_id = c.id
               WHERE t.status = %s
               ORDER BY t.due_date ASC NULLS LAST, t.priority DESC
               LIMIT %s""",
            (status, limit)
        ).fetchall()


def complete_task(task_id: int) -> bool:
    with _conn() as c:
        c.execute("UPDATE crm_tasks SET status = 'done' WHERE id = %s",
                  (task_id,))
        return c.rowcount > 0


# ─────────────────────────────────────────────────────────────────────────────
# Campaigns
# ─────────────────────────────────────────────────────────────────────────────

def create_campaign(title: str, *, description: str = "",
                    target_audience: str = "",
                    keywords: list[str] | None = None,
                    message_template: str = "") -> int:
    with _conn() as c:
        row = c.execute(
            """INSERT INTO crm_campaigns
               (title, description, target_audience, keywords, message_template)
               VALUES (%s, %s, %s, %s, %s) RETURNING id""",
            (title, description, target_audience, keywords or [],
             message_template)
        ).fetchone()
        return row["id"]


def get_campaign(campaign_id: int) -> dict | None:
    with _conn() as c:
        return c.execute(
            "SELECT * FROM crm_campaigns WHERE id = %s", (campaign_id,)
        ).fetchone()


def list_campaigns(limit: int = 20) -> list[dict]:
    with _conn() as c:
        return c.execute(
            "SELECT * FROM crm_campaigns ORDER BY created_at DESC LIMIT %s",
            (limit,)
        ).fetchall()


def add_campaign_contact(campaign_id: int, contact_id: int,
                         ai_score: float = 0.0,
                         ai_reason: str = "") -> None:
    with _conn() as c:
        c.execute(
            """INSERT INTO crm_campaign_contacts
               (campaign_id, contact_id, ai_score, ai_reason)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (campaign_id, contact_id) DO UPDATE
               SET ai_score = EXCLUDED.ai_score, ai_reason = EXCLUDED.ai_reason""",
            (campaign_id, contact_id, ai_score, ai_reason)
        )


def list_campaign_contacts(campaign_id: int) -> list[dict]:
    with _conn() as c:
        return c.execute(
            """SELECT cc.*, c.first_name, c.last_name, c.email, c.phone, c.telegram
               FROM crm_campaign_contacts cc
               JOIN crm_contacts c ON cc.contact_id = c.id
               WHERE cc.campaign_id = %s
               ORDER BY cc.ai_score DESC""",
            (campaign_id,)
        ).fetchall()


def update_campaign_status(campaign_id: int, status: str,
                           n8n_execution_id: str = "") -> bool:
    with _conn() as c:
        if n8n_execution_id:
            c.execute(
                "UPDATE crm_campaigns SET status = %s, n8n_execution_id = %s WHERE id = %s",
                (status, n8n_execution_id, campaign_id))
        else:
            c.execute(
                "UPDATE crm_campaigns SET status = %s WHERE id = %s",
                (status, campaign_id))
        return c.rowcount > 0


# ─────────────────────────────────────────────────────────────────────────────
# Stats
# ─────────────────────────────────────────────────────────────────────────────

def get_stats() -> dict:
    """Return CRM summary statistics."""
    with _conn() as c:
        contacts = c.execute("SELECT COUNT(*) AS cnt FROM crm_contacts").fetchone()["cnt"]
        active_tasks = c.execute(
            "SELECT COUNT(*) AS cnt FROM crm_tasks WHERE status = 'active'"
        ).fetchone()["cnt"]
        campaigns = c.execute("SELECT COUNT(*) AS cnt FROM crm_campaigns").fetchone()["cnt"]
        interactions = c.execute("SELECT COUNT(*) AS cnt FROM crm_interactions").fetchone()["cnt"]
    return {
        "contacts": contacts,
        "active_tasks": active_tasks,
        "campaigns": campaigns,
        "interactions": interactions,
    }
