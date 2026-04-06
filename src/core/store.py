"""
store.py — DataStore factory + module-level singleton.

Usage anywhere in the codebase:
    from core.store import store
    store.save_event(chat_id, event)
    store.append_history(chat_id, "user", text)

Backend is selected by STORE_BACKEND env var in bot.env:
    sqlite   (default — PicoClaw / ZeroClaw)
    postgres (OpenClaw — requires STORE_PG_DSN)

Dependency chain: bot_config → bot_db → store_base → store
"""

import os

from core.bot_config import log_datastore as log, TARIS_DIR
from core.store_base import DataStore


def create_store() -> DataStore:
    """Instantiate and return the configured storage adapter.

    Called once at module import time to create the singleton.
    Reads STORE_BACKEND and STORE_DB_PATH from the environment.
    """
    backend = os.environ.get("STORE_BACKEND", "sqlite").lower()

    if backend == "postgres":
        dsn = os.environ.get("STORE_PG_DSN", "")
        if not dsn:
            raise RuntimeError(
                "[Store] STORE_BACKEND=postgres but STORE_PG_DSN is not set"
            )
        log.info("[Store] Backend: PostgreSQL")
        from core.store_postgres import PostgresStore  # type: ignore[import]
        return PostgresStore(dsn=dsn)

    # Default: SQLite
    db_path = os.environ.get("STORE_DB_PATH") or os.path.join(TARIS_DIR, "taris.db")
    log.info("[Store] Backend: SQLite (%s)", db_path)
    from core.store_sqlite import SQLiteStore
    return SQLiteStore(db_path=db_path)


# ── Module-level singleton ────────────────────────────────────────────────────
# Imported by feature modules:   from core.store import store
store: DataStore = create_store()
