#!/usr/bin/env python3
"""Shared Telegram utilities for Copilot MCP tools and hooks."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


DEFAULT_TIMEOUT_SECONDS = 900
DEFAULT_LONG_POLL_SECONDS = 20
MESSAGE_LIMIT = 4096
SAFE_PART_LIMIT = 3500

# ---------------------------------------------------------------------------
# Task queue — file-based, survives MCP server restarts within the same container
# ---------------------------------------------------------------------------

_TASK_QUEUE_FILE = Path(
    os.environ.get("TASK_QUEUE_FILE", str(Path(tempfile.gettempdir()) / "taris_tasks.json"))
)
_TASK_QUEUE_LOCK = threading.Lock()


def _read_task_queue() -> list[dict[str, Any]]:
    with _TASK_QUEUE_LOCK:
        if not _TASK_QUEUE_FILE.exists():
            return []
        try:
            return json.loads(_TASK_QUEUE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []


def _write_task_queue(tasks: list[dict[str, Any]]) -> None:
    with _TASK_QUEUE_LOCK:
        _TASK_QUEUE_FILE.write_text(json.dumps(tasks, ensure_ascii=False), encoding="utf-8")


def queue_task(text: str, from_user: str = "telegram") -> None:
    """Append a task to the queue (called by background listener)."""
    tasks = _read_task_queue()
    tasks.append({"text": text, "from_user": from_user, "ts": time.time()})
    _write_task_queue(tasks)


def pop_task() -> Optional[dict[str, Any]]:
    """Remove and return the oldest pending task, or None if empty."""
    with _TASK_QUEUE_LOCK:
        if not _TASK_QUEUE_FILE.exists():
            return None
        try:
            tasks = json.loads(_TASK_QUEUE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not tasks:
            return None
        task = tasks.pop(0)
        _TASK_QUEUE_FILE.write_text(json.dumps(tasks, ensure_ascii=False), encoding="utf-8")
        return task


def peek_task_queue() -> list[dict[str, Any]]:
    """Return all queued tasks without removing them."""
    return _read_task_queue()


def _truncate(text: str, limit: int = 2000) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _split_text(text: str, max_len: int = SAFE_PART_LIMIT) -> list[str]:
    if not text:
        return []
    parts: list[str] = []
    rest = text
    while rest:
        if len(rest) <= max_len:
            parts.append(rest)
            break
        cut = rest.rfind("\n", 0, max_len)
        if cut <= 0:
            cut = max_len
        parts.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    return parts


def _parse_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _load_env_file(cwd: Optional[str]) -> dict[str, str]:
    if not cwd:
        return {}
    env_path = Path(cwd) / ".env"
    if not env_path.exists():
        return {}

    data: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        data[key] = value
    return data


@dataclass
class BridgeConfig:
    bot_token: str
    chat_id: Optional[int]
    default_timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    long_poll_seconds: int = DEFAULT_LONG_POLL_SECONDS
    vps_host: Optional[str] = None  # set → always-on VPS docker container is polling

    @classmethod
    def from_env(cls, cwd: Optional[str] = None) -> "BridgeConfig":
        env_file = _load_env_file(cwd)

        def get_value(*keys: str) -> Optional[str]:
            for key in keys:
                if key in os.environ and os.environ[key]:
                    return os.environ[key]
                if key in env_file and env_file[key]:
                    return env_file[key]
            return None

        bot_token = get_value("TELEGRAM_BOT_TOKEN", "TG_BOT_TOKEN") or ""
        chat_id = _parse_int(get_value("TELEGRAM_CHAT_ID", "TG_CHAT_ID"))
        timeout = _parse_int(
            get_value("TELEGRAM_TIMEOUT_SECONDS", "TELEGRAM_APPROVAL_TIMEOUT_SECONDS")
        )
        long_poll = _parse_int(get_value("TELEGRAM_LONG_POLL_SECONDS"))
        vps_host = get_value("VPS_MCP_HOST")

        return cls(
            bot_token=bot_token.strip(),
            chat_id=chat_id,
            default_timeout_seconds=timeout or DEFAULT_TIMEOUT_SECONDS,
            long_poll_seconds=long_poll or DEFAULT_LONG_POLL_SECONDS,
            vps_host=vps_host,
        )

    def is_ready(self) -> bool:
        return bool(self.bot_token and self.chat_id is not None)


class TelegramBridge:
    """Long-poll Telegram client with unified update dispatcher.

    A single background thread polls for all updates and routes them to:
    - The file-based task queue (for /task commands)
    - Per-token response events (for wait_for_response callers)

    This design avoids 409 Conflict errors from concurrent getUpdates calls.
    """

    def __init__(self, config: BridgeConfig):
        self.config = config
        self.base_url = f"https://api.telegram.org/bot{config.bot_token}"
        self._last_update_id: Optional[int] = None
        self._dispatcher_started = False

        # Per-token mailboxes: token → (event, result_container)
        self._pending: dict[str, tuple[threading.Event, list[dict[str, Any]]]] = {}
        self._pending_lock = threading.Lock()
        # Prompt message IDs per token: token → set[int]
        self._prompt_ids: dict[str, set[int]] = {}

    @staticmethod
    def new_token() -> str:
        return uuid.uuid4().hex[:8].upper()

    def _api(self, method: str, payload: dict[str, Any]) -> Any:
        url = f"{self.base_url}/{method}"
        request_data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=request_data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=70) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Telegram HTTP error {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Telegram connection error: {exc.reason}") from exc

        if not body.get("ok"):
            description = body.get("description", "unknown Telegram API error")
            raise RuntimeError(f"Telegram API error: {description}")
        return body.get("result")

    # ------------------------------------------------------------------
    # Unified dispatcher (single getUpdates loop)
    # ------------------------------------------------------------------

    def start_dispatcher(self) -> None:
        """Start the background update dispatcher (idempotent)."""
        if self._dispatcher_started:
            return
        self._dispatcher_started = True
        t = threading.Thread(target=self._dispatcher_loop, daemon=True, name="tg-dispatcher")
        t.start()

    def _dispatcher_loop(self) -> None:
        poll_seconds = self.config.long_poll_seconds
        while True:
            try:
                updates = self._fetch_updates(timeout_seconds=poll_seconds)
                for update in updates:
                    self._dispatch(update)
            except Exception:
                time.sleep(5)

    def _fetch_updates(self, timeout_seconds: int) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"timeout": max(1, timeout_seconds)}
        if self._last_update_id is not None:
            payload["offset"] = self._last_update_id + 1
        updates = self._api("getUpdates", payload) or []
        for update in updates:
            update_id = update.get("update_id")
            if isinstance(update_id, int):
                if self._last_update_id is None or update_id > self._last_update_id:
                    self._last_update_id = update_id
        return updates

    def _dispatch(self, update: dict[str, Any]) -> None:
        """Route an update to waiting tokens or the task queue."""
        # Extract message and callback info
        message: dict[str, Any] = {}
        callback_data: Optional[str] = None
        callback_from_data: Optional[dict] = None

        if "message" in update:
            message = update["message"] or {}
        elif "edited_message" in update:
            message = update["edited_message"] or {}
        elif "callback_query" in update:
            cq = update["callback_query"] or {}
            message = cq.get("message") or {}
            callback_data = cq.get("data")
            callback_id = cq.get("id")
            callback_from_data = cq.get("from") or {}
            if callback_id:
                self._safe_answer_callback(callback_id)
        else:
            return

        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        if self.config.chat_id is not None and chat_id != self.config.chat_id:
            return

        from_data = callback_from_data if callback_from_data is not None else (message.get("from") or {})
        from_user = from_data.get("username") or from_data.get("first_name") or "unknown"
        message_id = message.get("message_id")

        text = (message.get("text") or "").strip()
        if callback_data:
            text = callback_data.strip()
        if not text:
            return

        reply_to_id = None
        reply_to = message.get("reply_to_message") or {}
        if isinstance(reply_to.get("message_id"), int):
            reply_to_id = reply_to["message_id"]

        command, arg_token, remainder = self._parse_command(text)

        # --- Task queue: /task <text> ---
        if command == "task":
            task_text = remainder.strip() if remainder.strip() else text[len("/task"):].strip()
            if task_text:
                queue_task(task_text, from_user=str(from_user))
                try:
                    self._send_text(
                        f"✅ Task queued for Copilot:\n_{task_text}_\n\nCopilot will pick it up on next session start.",
                    )
                except Exception:
                    pass
            return

        # --- Token-based response routing ---
        with self._pending_lock:
            pending_tokens = list(self._pending.keys())

        for token in pending_tokens:
            prompt_message_ids = self._prompt_ids.get(token, set())
            token_matches = arg_token == token if arg_token else False
            replied_to_prompt = reply_to_id in prompt_message_ids if reply_to_id is not None else False

            # Determine mode from pending registration (stored as first char of event name)
            with self._pending_lock:
                if token not in self._pending:
                    continue
                event, result_box = self._pending[token]

            mode = self._token_mode.get(token, "question")
            parsed = self._try_parse_response(
                mode=mode,
                token=token,
                text=text,
                command=command,
                arg_token=arg_token,
                remainder=remainder,
                token_matches=token_matches,
                replied_to_prompt=replied_to_prompt,
                from_user=str(from_user),
                chat_id=chat_id,
                message_id=message_id,
            )
            if parsed is not None:
                result_box.append(parsed)
                event.set()
                return

    def _try_parse_response(
        self,
        *,
        mode: str,
        token: str,
        text: str,
        command: str,
        arg_token: str,
        remainder: str,
        token_matches: bool,
        replied_to_prompt: bool,
        from_user: str,
        chat_id: Any,
        message_id: Any,
    ) -> Optional[dict[str, Any]]:
        base = {
            "status": "received",
            "mode": mode,
            "token": token,
            "from_user": from_user,
            "chat_id": chat_id,
            "message_id": message_id,
        }
        if mode == "approval":
            if command in {"allow", "deny", "ask"} and (token_matches or replied_to_prompt):
                return {**base, "decision": command, "text": remainder.strip()}
            if replied_to_prompt:
                normalized = text.strip().lower()
                if normalized in {"allow", "yes", "ok", "approve"}:
                    return {**base, "decision": "allow", "text": ""}
                if normalized in {"deny", "no", "reject"}:
                    return {**base, "decision": "deny", "text": ""}
            return None
        # question mode
        if command == "reply" and token_matches and remainder.strip():
            return {**base, "decision": "answer", "text": remainder.strip()}
        if replied_to_prompt and text:
            return {**base, "decision": "answer", "text": text}
        return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send_wait_prompt(
        self,
        *,
        mode: str,
        token: str,
        question: str,
        last_chat_text: str,
    ) -> list[int]:
        if self.config.chat_id is None:
            raise RuntimeError("TELEGRAM_CHAT_ID is not configured")

        mode = mode.strip().lower()
        message_ids: list[int] = []

        if mode == "approval":
            q_text = f"\n\n{question.strip()}" if question.strip() else ""
            header = f"🔔 Copilot approval request\nToken: `{token}`{q_text}"
            reply_markup = {
                "inline_keyboard": [[
                    {"text": "✅ Allow", "callback_data": f"/allow{token}"},
                    {"text": "❌ Deny",  "callback_data": f"/deny{token}"},
                    {"text": "❓ Ask",   "callback_data": f"/ask{token}"},
                ]]
            }
            message_ids.append(self._send_text(header, reply_markup=reply_markup))
            if last_chat_text.strip():
                chunks = _split_text(last_chat_text.strip(), SAFE_PART_LIMIT)
                for index, chunk in enumerate(chunks, start=1):
                    label = "Context" if len(chunks) == 1 else f"Context (part {index}/{len(chunks)})"
                    message_ids.append(self._send_text(f"{label}:\n{chunk}"))
        else:
            reply_help = f"/reply {token} <your message>"
            header = (
                "Copilot requires input via Telegram.\n"
                f"Mode: {mode}\n"
                f"Token: {token}\n\n"
                f"Reply format:\n{reply_help}"
            )
            message_ids.append(self._send_text(header))
            for prefix, text in (("Question:", question), ("Last chat text:", last_chat_text)):
                if not text:
                    continue
                chunks = _split_text(text, SAFE_PART_LIMIT)
                for index, chunk in enumerate(chunks, start=1):
                    label = prefix if len(chunks) == 1 else f"{prefix} (part {index}/{len(chunks)})"
                    message_ids.append(self._send_text(f"{label}\n{chunk}"))

        return message_ids

    def _send_text(self, text: str, reply_markup: Optional[dict] = None) -> int:
        payload: dict[str, Any] = {
            "chat_id": self.config.chat_id,
            "text": _truncate(text, MESSAGE_LIMIT - 16),
            "disable_web_page_preview": True,
            "parse_mode": "Markdown",
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        result = self._api("sendMessage", payload)
        return int(result["message_id"])

    def send_notification(self, text: str) -> int:
        return self._send_text(text)

    def send_notification_text(self, text: str) -> list[int]:
        chunks = _split_text(text, SAFE_PART_LIMIT)
        return [self._send_text(chunk) for chunk in chunks if chunk.strip()]

    def wait_for_response(
        self,
        *,
        token: str,
        mode: str,
        prompt_message_ids: Optional[list[int]] = None,
        timeout_seconds: Optional[int] = None,
    ) -> dict[str, Any]:
        """Wait for a token-matched response from the dispatcher.

        If the dispatcher is running (SSE/VPS mode), this registers a mailbox and
        waits for the dispatcher to deliver the result. If the dispatcher is NOT
        running (stdio/local mode), falls back to the legacy polling loop.
        """
        mode = mode.strip().lower()
        timeout = timeout_seconds or self.config.default_timeout_seconds
        self._prompt_ids[token] = set(prompt_message_ids or [])

        if self._dispatcher_started:
            # Dispatcher mode: register and wait
            event: threading.Event = threading.Event()
            result_box: list[dict[str, Any]] = []
            with self._pending_lock:
                self._pending[token] = (event, result_box)
            if not hasattr(self, "_token_mode"):
                self._token_mode: dict[str, str] = {}
            self._token_mode[token] = mode
            try:
                got = event.wait(timeout=timeout)
                if got and result_box:
                    return result_box[0]
                return {"status": "timeout", "token": token, "mode": mode}
            finally:
                with self._pending_lock:
                    self._pending.pop(token, None)
                self._prompt_ids.pop(token, None)
                self._token_mode.pop(token, None)
        else:
            # Legacy mode: poll directly (no dispatcher running)
            return self._poll_for_response(
                token=token, mode=mode,
                prompt_message_ids=list(prompt_message_ids or []),
                timeout=timeout,
            )

    def _poll_for_response(
        self,
        *,
        token: str,
        mode: str,
        prompt_message_ids: list[int],
        timeout: int,
    ) -> dict[str, Any]:
        """Direct polling loop — used in stdio mode (no dispatcher)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            remaining = max(1, int(deadline - time.time()))
            long_poll = min(self.config.long_poll_seconds, remaining)
            updates = self._fetch_updates(timeout_seconds=long_poll)
            for update in updates:
                parsed = self._dispatch_to_response(
                    update=update,
                    token=token,
                    mode=mode,
                    prompt_message_ids=set(prompt_message_ids),
                )
                if parsed is not None:
                    return parsed
        return {"status": "timeout", "token": token, "mode": mode}

    def _dispatch_to_response(
        self,
        *,
        update: dict[str, Any],
        token: str,
        mode: str,
        prompt_message_ids: set[int],
    ) -> Optional[dict[str, Any]]:
        message: dict[str, Any] = {}
        callback_data: Optional[str] = None
        callback_from_data: Optional[dict] = None

        if "message" in update:
            message = update["message"] or {}
        elif "edited_message" in update:
            message = update["edited_message"] or {}
        elif "callback_query" in update:
            cq = update["callback_query"] or {}
            message = cq.get("message") or {}
            callback_data = cq.get("data")
            callback_id = cq.get("id")
            callback_from_data = cq.get("from") or {}
            if callback_id:
                self._safe_answer_callback(callback_id)
        else:
            return None

        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        if self.config.chat_id is not None and chat_id != self.config.chat_id:
            return None

        from_data = callback_from_data if callback_from_data is not None else (message.get("from") or {})
        from_user = from_data.get("username") or from_data.get("first_name") or "unknown"
        message_id = message.get("message_id")
        text = (message.get("text") or "").strip()
        if callback_data:
            text = callback_data.strip()
        if not text:
            return None

        reply_to_id = None
        reply_to = message.get("reply_to_message") or {}
        if isinstance(reply_to.get("message_id"), int):
            reply_to_id = reply_to["message_id"]

        command, arg_token, remainder = self._parse_command(text)
        token_matches = arg_token == token if arg_token else False
        replied_to_prompt = reply_to_id in prompt_message_ids if reply_to_id is not None else False

        return self._try_parse_response(
            mode=mode,
            token=token,
            text=text,
            command=command,
            arg_token=arg_token,
            remainder=remainder,
            token_matches=token_matches,
            replied_to_prompt=replied_to_prompt,
            from_user=str(from_user),
            chat_id=chat_id,
            message_id=message_id,
        )

    def _safe_answer_callback(self, callback_id: str) -> None:
        try:
            self._api("answerCallbackQuery", {"callback_query_id": callback_id})
        except Exception:
            pass

    @staticmethod
    def _parse_command(text: str) -> tuple[str, str, str]:
        normalized = text.strip()
        if not normalized.startswith("/"):
            return "", "", normalized

        pieces = normalized.split(" ", 2)
        raw_command = pieces[0][1:]  # everything after the leading /

        # Support no-space format: /allowTOKEN /denyTOKEN /askTOKEN /replyTOKEN
        _KNOWN_VERBS = ("allow", "deny", "ask", "reply", "task")
        command = ""
        inline_token = ""
        for verb in _KNOWN_VERBS:
            if raw_command.lower().startswith(verb):
                suffix = raw_command[len(verb):]
                if suffix and not suffix[0].isspace():
                    command = verb
                    inline_token = suffix.upper()
                    break
                elif not suffix:
                    command = verb
                    break
        if not command:
            command = raw_command.strip().lower()

        if inline_token:
            remainder = " ".join(pieces[1:]) if len(pieces) > 1 else ""
            return command, inline_token, remainder

        token = pieces[1].strip().upper() if len(pieces) > 1 else ""
        remainder = pieces[2] if len(pieces) > 2 else ""
        return command, token, remainder

    # ------------------------------------------------------------------
    # start_task_listener — kept for backward compat, now starts dispatcher
    # ------------------------------------------------------------------

    def start_task_listener(self) -> threading.Thread:
        """Start the unified dispatcher (includes /task listening). Idempotent."""
        self.start_dispatcher()
        # Return a dummy thread reference for backward compat
        return threading.current_thread()
