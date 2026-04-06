"""
bot_auth.py — Web authentication: accounts, passwords, JWT tokens, password reset.

Provides:
  - Account CRUD backed by DB (web_accounts table — SQLite or Postgres)
  - bcrypt password hashing (work factor 12)
  - PyJWT token create / verify (HS256, 24 h expiry)
  - Optional Telegram linking (chat_id ↔ user_id)
  - Password reset tokens (60 min TTL, web_reset_tokens table)
"""

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import bcrypt
import jwt

from core.bot_config import log_security as log, TARIS_DIR

# ─────────────────────────────────────────────────────────────────────────────
# Paths (kept for migration fallback)
# ─────────────────────────────────────────────────────────────────────────────

_TARIS_DIR = TARIS_DIR
ACCOUNTS_FILE = os.path.join(TARIS_DIR, "accounts.json")
_SECRET_FILE  = os.path.join(TARIS_DIR, "web_secret.key")

JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24
COOKIE_NAME = "taris_token"

# ─────────────────────────────────────────────────────────────────────────────
# JWT secret — generated once, persisted
# ─────────────────────────────────────────────────────────────────────────────

def _get_jwt_secret() -> str:
    """Return the JWT signing secret; generate and persist if absent."""
    try:
        return Path(_SECRET_FILE).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        secret = uuid.uuid4().hex + uuid.uuid4().hex  # 64 hex chars
        Path(_SECRET_FILE).parent.mkdir(parents=True, exist_ok=True)
        Path(_SECRET_FILE).write_text(secret, encoding="utf-8")
        os.chmod(_SECRET_FILE, 0o600)
        log.info("[Auth] Generated new JWT secret")
        return secret


_JWT_SECRET: str = _get_jwt_secret()


# ─────────────────────────────────────────────────────────────────────────────
# Store accessor (lazy to avoid circular import)
# ─────────────────────────────────────────────────────────────────────────────

def _store():
    from core.store import store as _s  # noqa: PLC0415
    return _s


# ─────────────────────────────────────────────────────────────────────────────
# Account storage — DB backed (web_accounts table)
# ─────────────────────────────────────────────────────────────────────────────

def find_account_by_username(username: str) -> Optional[dict]:
    return _store().find_web_account(username=username)


def find_account_by_id(user_id: str) -> Optional[dict]:
    return _store().find_web_account(user_id=user_id)


def find_account_by_chat_id(chat_id: int) -> Optional[dict]:
    return _store().find_web_account(chat_id=chat_id)


def create_account(username: str, password: str, display_name: str = "",
                   role: str = "user", telegram_chat_id: Optional[int] = None,
                   status: str = "active") -> dict:
    """Create a new account with hashed password.  Returns the account dict."""
    user_id = "u-" + uuid.uuid4().hex[:8]
    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12))
    account = {
        "user_id":           user_id,
        "username":          username.lower(),
        "display_name":      display_name or username,
        "pw_hash":           pw_hash.decode("utf-8"),
        "role":              role,
        "status":            status,
        "telegram_chat_id":  telegram_chat_id,
        "created":           datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "is_approved":       True,
    }
    _store().upsert_web_account(account)
    log.info(f"[Auth] Created account {user_id} ({username}) status={status}")
    return account


def verify_password(account: dict, password: str) -> bool:
    """Check password against stored bcrypt hash."""
    stored = account.get("pw_hash", "")
    return bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8"))


def update_account(user_id: str, **fields) -> bool:
    """Update fields on an existing account.  Returns True if found."""
    return _store().update_web_account(user_id, **fields)


def list_accounts() -> list[dict]:
    """Return all accounts (password hashes included — filter in caller)."""
    return _store().list_web_accounts()


def change_password(user_id: str, new_password: str) -> bool:
    """Replace the stored bcrypt hash for the given user_id.  Returns True if found."""
    new_hash = bcrypt.hashpw(
        new_password.encode("utf-8"), bcrypt.gensalt(rounds=12)
    ).decode("utf-8")
    return update_account(user_id, pw_hash=new_hash)


def change_username(user_id: str, new_username: str) -> str:
    """Rename a web account.  Returns 'ok', 'taken', or 'not_found'."""
    new_lc = new_username.strip().lower()
    if not new_lc:
        return "not_found"
    if find_account_by_username(new_lc):
        return "taken"
    if not find_account_by_id(user_id):
        return "not_found"
    _store().update_web_account(user_id, username=new_lc)
    log.info(f"[Auth] Username changed to '{new_lc}' for user_id={user_id}")
    return "ok"


# ─────────────────────────────────────────────────────────────────────────────
# Telegram ↔ Web linking codes  (6-char, 10 min TTL)
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# JWT tokens
# ─────────────────────────────────────────────────────────────────────────────

def create_token(user_id: str, username: str, role: str = "user") -> str:
    """Create a signed JWT with 24 h expiry."""
    payload = {
        "sub":      user_id,
        "username": username,
        "role":     role,
        "exp":      datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
        "iat":      datetime.now(timezone.utc),
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> Optional[dict]:
    """Decode and verify a JWT.  Returns payload dict or None on failure."""
    try:
        return jwt.decode(token, _JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Password reset tokens  (TTL = 60 min, stored in web_reset_tokens table)
# ─────────────────────────────────────────────────────────────────────────────

RESET_TOKEN_TTL_MIN = 60


def generate_reset_token(username: str) -> Optional[str]:
    """Generate a one-time reset token (60 min TTL).  Returns token str, or None if user not found."""
    account = find_account_by_username(username)
    if not account:
        return None
    token   = uuid.uuid4().hex + uuid.uuid4().hex[:8]   # 40-char hex
    expires = (datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_TTL_MIN)).isoformat()
    _store().delete_reset_tokens_for_user(username)
    _store().save_reset_token(token, username, expires)
    log.info(f"[Auth] Reset token generated for '{username}'")
    return token


def validate_reset_token(token: str) -> Optional[str]:
    """Return username if token is valid and not expired; None otherwise."""
    row = _store().find_reset_token(token)
    if not row:
        return None
    try:
        exp = datetime.fromisoformat(str(row["expires"]))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) < exp:
            return row["username"]
    except (KeyError, ValueError):
        pass
    return None


def consume_reset_token(token: str) -> Optional[str]:
    """Mark token used and return username; returns None if invalid/expired."""
    username = validate_reset_token(token)
    if username:
        _store().mark_reset_token_used(token)
    return username


# ─────────────────────────────────────────────────────────────────────────────
# Bootstrap: ensure at least one admin account exists
# ─────────────────────────────────────────────────────────────────────────────

def ensure_admin_account() -> None:
    """Import accounts.json to DB if web_accounts is empty, then ensure an admin exists."""
    # Auto-migrate from accounts.json on first run
    if not _store().list_web_accounts():
        try:
            data = json.loads(Path(ACCOUNTS_FILE).read_text(encoding="utf-8"))
            imported = data.get("accounts", [])
            for acc in imported:
                if "is_approved" not in acc:
                    acc["is_approved"] = True
                _store().upsert_web_account(acc)
            if imported:
                log.info(f"[Auth] Migrated {len(imported)} account(s) from accounts.json to DB")
                return
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    if _store().list_web_accounts():
        return
    create_account("admin", "admin", display_name="Admin", role="admin")
    log.info("[Auth] Created default admin account (admin/admin) — change password!")
