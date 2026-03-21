"""
bot_auth.py — Web authentication: accounts, passwords, JWT tokens.

Provides:
  - Account CRUD backed by ~/.taris/accounts.json
  - bcrypt password hashing (work factor 12)
  - PyJWT token create / verify (HS256, 24 h expiry)
  - Optional Telegram linking (chat_id ↔ user_id)
"""

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import bcrypt
import jwt

from core.bot_config import log

# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────

_TARIS_DIR = os.path.expanduser("~/.taris")
ACCOUNTS_FILE = os.path.join(_TARIS_DIR, "accounts.json")
_SECRET_FILE  = os.path.join(_TARIS_DIR, "web_secret.key")

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
# Account storage
# ─────────────────────────────────────────────────────────────────────────────

def _load_accounts() -> list[dict]:
    try:
        data = json.loads(Path(ACCOUNTS_FILE).read_text(encoding="utf-8"))
        return data.get("accounts", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_accounts(accounts: list[dict]) -> None:
    Path(ACCOUNTS_FILE).parent.mkdir(parents=True, exist_ok=True)
    Path(ACCOUNTS_FILE).write_text(
        json.dumps({"accounts": accounts}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def find_account_by_username(username: str) -> Optional[dict]:
    username_lower = username.lower()
    for a in _load_accounts():
        if a.get("username", "").lower() == username_lower:
            return a
    return None


def find_account_by_id(user_id: str) -> Optional[dict]:
    for a in _load_accounts():
        if a.get("user_id") == user_id:
            return a
    return None


def find_account_by_chat_id(chat_id: int) -> Optional[dict]:
    for a in _load_accounts():
        if a.get("telegram_chat_id") == chat_id:
            return a
    return None


def create_account(username: str, password: str, display_name: str = "",
                   role: str = "user", telegram_chat_id: Optional[int] = None,
                   status: str = "active") -> dict:
    """Create a new account with hashed password.  Returns the account dict."""
    accounts = _load_accounts()
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
    }
    accounts.append(account)
    _save_accounts(accounts)
    log.info(f"[Auth] Created account {user_id} ({username}) status={status}")
    return account


def verify_password(account: dict, password: str) -> bool:
    """Check password against stored bcrypt hash."""
    stored = account.get("pw_hash", "")
    return bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8"))


def update_account(user_id: str, **fields) -> bool:
    """Update fields on an existing account.  Returns True if found."""
    accounts = _load_accounts()
    for a in accounts:
        if a.get("user_id") == user_id:
            a.update(fields)
            _save_accounts(accounts)
            return True
    return False


def list_accounts() -> list[dict]:
    """Return all accounts (password hashes included — filter in caller)."""
    return _load_accounts()


def change_password(user_id: str, new_password: str) -> bool:
    """Replace the stored bcrypt hash for the given user_id.  Returns True if found."""
    new_hash = bcrypt.hashpw(
        new_password.encode("utf-8"), bcrypt.gensalt(rounds=12)
    ).decode("utf-8")
    return update_account(user_id, pw_hash=new_hash)


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
# Bootstrap: ensure at least one admin account exists
# ─────────────────────────────────────────────────────────────────────────────

def ensure_admin_account() -> None:
    """If no accounts exist, create a default admin (admin / admin).
    The admin should change the password on first login."""
    accounts = _load_accounts()
    if accounts:
        return
    create_account("admin", "admin", display_name="Admin", role="admin")
    log.info("[Auth] Created default admin account (admin/admin) — change password!")
