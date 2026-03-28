"""
bot_auth.py — Web authentication: accounts, passwords, JWT tokens, password reset.

Provides:
  - Account CRUD backed by ~/.taris/accounts.json
  - bcrypt password hashing (work factor 12)
  - PyJWT token create / verify (HS256, 24 h expiry)
  - Optional Telegram linking (chat_id ↔ user_id)
  - Password reset tokens (60 min TTL, stored in reset_tokens.json)
"""

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import bcrypt
import jwt

from core.bot_config import log, TARIS_DIR

# ─────────────────────────────────────────────────────────────────────────────
# Paths
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


def change_username(user_id: str, new_username: str) -> str:
    """Rename a web account.  Returns 'ok', 'taken', or 'not_found'."""
    new_lc = new_username.strip().lower()
    if not new_lc:
        return "not_found"
    accounts = _load_accounts()
    existing_user = None
    for a in accounts:
        if a.get("user_id") == user_id:
            existing_user = a
        elif a.get("username", "").lower() == new_lc:
            return "taken"
    if not existing_user:
        return "not_found"
    existing_user["username"] = new_lc
    _save_accounts(accounts)
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
# Password reset tokens  (TTL = 60 min, stored in reset_tokens.json)
# ─────────────────────────────────────────────────────────────────────────────

_RESET_TOKENS_FILE  = os.path.join(TARIS_DIR, "reset_tokens.json")
RESET_TOKEN_TTL_MIN = 60


def _load_reset_tokens() -> list[dict]:
    try:
        return json.loads(Path(_RESET_TOKENS_FILE).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_reset_tokens(tokens: list[dict]) -> None:
    Path(_RESET_TOKENS_FILE).parent.mkdir(parents=True, exist_ok=True)
    Path(_RESET_TOKENS_FILE).write_text(json.dumps(tokens, indent=2), encoding="utf-8")


def generate_reset_token(username: str) -> Optional[str]:
    """Generate a one-time reset token (60 min TTL).  Returns token str, or None if user not found."""
    account = find_account_by_username(username)
    if not account:
        return None
    token   = uuid.uuid4().hex + uuid.uuid4().hex[:8]   # 40-char hex
    expires = (datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_TTL_MIN)).isoformat()
    tokens  = [t for t in _load_reset_tokens() if t.get("username") != username.lower()]
    tokens.append({"token": token, "username": username.lower(), "expires": expires, "used": False})
    _save_reset_tokens(tokens)
    log.info(f"[Auth] Reset token generated for '{username}'")
    return token


def validate_reset_token(token: str) -> Optional[str]:
    """Return username if token is valid and not expired; None otherwise."""
    now = datetime.now(timezone.utc)
    for t in _load_reset_tokens():
        if t.get("token") == token and not t.get("used"):
            try:
                exp = datetime.fromisoformat(t["expires"])
                if now < exp:
                    return t["username"]
            except (KeyError, ValueError):
                pass
    return None


def consume_reset_token(token: str) -> Optional[str]:
    """Mark token used and return username; returns None if invalid/expired."""
    tokens   = _load_reset_tokens()
    username = None
    now      = datetime.now(timezone.utc)
    for t in tokens:
        if t.get("token") == token and not t.get("used"):
            try:
                exp = datetime.fromisoformat(t["expires"])
                if now < exp:
                    username  = t["username"]
                    t["used"] = True
                    break
            except (KeyError, ValueError):
                pass
    _save_reset_tokens(tokens)
    return username


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
