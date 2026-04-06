# Taris — Developer Guide

**Audience:** Developers adding features, fixing bugs, or integrating new components into the Taris bot.  
**Scope:** Daily development workflow across both deployment platforms (OpenClaw and PicoClaw).  
→ Architecture reference: [architecture.md](architecture.md)  
→ Code patterns (copy-paste): [dev-patterns.md](dev-patterns.md)  
→ Quick reference card: [quick-ref.md](quick-ref.md)  
→ Test suite reference: [test-suite.md](test-suite.md)

---

## Table of Contents

1. [Platforms Overview](#1-platforms-overview)
2. [Development Environment Setup](#2-development-environment-setup)
3. [Repository Layout](#3-repository-layout)
4. [Daily Development Workflow](#4-daily-development-workflow)
5. [Writing Features — Step-by-Step](#5-writing-features--step-by-step)
6. [Debugging](#6-debugging)
   - [6.8 IDE Debugger Attach (VS Code / PyCharm / Eclipse)](#68-ide-debugger-attach-vs-code--pycharm--eclipse)
7. [Testing](#7-testing)
8. [Deployment](#8-deployment)
9. [Platform-Specific Behaviour](#9-platform-specific-behaviour)
10. [LLM Integration Patterns](#10-llm-integration-patterns)
11. [Voice Pipeline Integration](#11-voice-pipeline-integration)
12. [i18n / Strings](#12-i18n--strings)
13. [Release Process](#13-release-process)
14. [Common Pitfalls](#14-common-pitfalls)

---

## 1. Platforms Overview

Taris runs on two hardware platforms, controlled by a single env-var:

```
DEVICE_VARIANT=picoclaw   # Raspberry Pi (default if unset)
DEVICE_VARIANT=openclaw   # Laptop / x86_64 PC
```

| Aspect | PicoClaw | OpenClaw |
|---|---|---|
| Hardware | Raspberry Pi 3 / 4 / 5 | Laptop / Mini-PC x86_64 |
| STT (hotword) | Vosk small-ru | Vosk small-ru |
| STT (commands) | Vosk | faster-whisper |
| TTS | Piper ONNX | Piper ONNX |
| LLM default | `taris` CLI → OpenRouter | `ollama` (Qwen2, local) |
| Local LLM | llama.cpp via `taris-llm.service` | Ollama (`~/.local/bin/ollama`) |
| Web UI | FastAPI :8080 (HTTPS) | FastAPI :8080 (HTTP) |
| REST API `/api/*` | ❌ not exposed | ✅ Bearer token |
| Skills gateway | ❌ | ✅ `sintaris-openclaw` :18789 |
| Deploy method | SSH + SCP (`plink`/`pscp`) | `cp` + `systemctl --user` |
| Dev target | `OpenClawPI2` | `TariStation2` (local) |
| Prod target | `OpenClawPI` | `TariStation1` / `SintAItion` |

**Rule: always deploy and test on the engineering target first. Production receives code only after tests pass.**

---

## 2. Development Environment Setup

### 2.1 OpenClaw (local development — TariStation2)

TariStation2 is the local machine. No SSH required — use `cp` to deploy.

**Prerequisites:**

```bash
# Python 3.11+, pip packages
pip install --user pyTelegramBotAPI fastapi uvicorn aiofiles python-jose python-multipart
pip install --user faster-whisper vosk piper-tts

# Ollama (local LLM)
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull qwen2:0.5b

# systemd user services (taris-telegram, taris-web, ollama)
systemctl --user enable taris-telegram taris-web
```

**Environment file:** `~/.taris/bot.env`

```bash
BOT_TOKEN=<your-telegram-token>
ALLOWED_USERS=<your-telegram-id>
DEVICE_VARIANT=openclaw
LLM_PROVIDER=ollama
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2:0.5b
STT_PROVIDER=faster_whisper
FASTER_WHISPER_MODEL=small
```

**Deploy source to TARIS_HOME:**

```bash
# Map from source → deployed path
cp src/core/bot_config.py     ~/.taris/core/
cp src/features/bot_voice.py  ~/.taris/features/
cp src/telegram/*.py          ~/.taris/telegram/
cp src/bot_web.py             ~/.taris/
cp src/web/templates/*.html   ~/.taris/web/templates/
systemctl --user restart taris-telegram taris-web
```

**Verify sync before restart:**

```bash
for f in src/bot_web.py src/core/bot_config.py src/telegram/bot_access.py; do
  diff "$f" ~/.taris/"${f#src/}" > /dev/null && echo "OK $f" || echo "DIFF $f"
done
```

### 2.2 PicoClaw (remote — OpenClawPI2)

PI2 is reached via SSH. Use `plink`/`pscp` (Windows) or `ssh`/`scp` (Linux/Mac).

**Prerequisites on dev machine:**
- PuTTY tools (`plink`, `pscp`) or openssh
- `.env` in repo root with `HOSTPWD`, `DEV_TARGETHOST`, etc. (gitignored)

**Deploy single file:**

```bash
# Linux/Mac:
scp src/features/bot_voice.py stas@OpenClawPI2:/home/stas/.taris/features/
ssh stas@OpenClawPI2 "sudo systemctl restart taris-telegram"

# Windows (plink/pscp):
pscp -pw "%HOSTPWD%" src\features\bot_voice.py stas@OpenClawPI2:/home/stas/.taris/features/
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI2 "echo %HOSTPWD% | sudo -S systemctl restart taris-telegram"
```

### 2.3 Running Tests Locally

Voice regression tests can be run from the repo root:

```bash
cd ~/projects/sintaris-pl
PYTHONPATH=src python3 src/tests/test_voice_regression.py
# or single test:
PYTHONPATH=src python3 src/tests/test_voice_regression.py --test t_voice_history_context
```

Most tests use **source file inspection** (not live imports) so they run correctly even when `~/.taris/` has a different version than `src/`.

**Playwright UI tests** (OpenClaw only):

```bash
pip install playwright pytest-playwright
playwright install chromium
pytest src/tests/ui/test_ui.py -v --base-url http://localhost:8080
```

---

## 3. Repository Layout

```
sintaris-pl/
  src/
    core/                ← shared: config, LLM, state, DB, auth
      bot_config.py      ← ALL constants, env-vars, variant switches
      bot_llm.py         ← LLM router: ask_llm(), ask_llm_with_history()
      bot_state.py       ← in-process state + conversation history
      bot_db.py          ← SQLite persistence layer
      bot_instance.py    ← singleton Telegram bot object
      rag_settings.py    ← runtime-configurable RAG parameters
      bot_prompts.py     ← loads prompts.json (system prompts, lang instructions)
    telegram/            ← Telegram channel: access, handlers, admin, users
      bot_access.py      ← _t(), _is_allowed(), _is_admin(), prompt builders, RAG context
      bot_handlers.py    ← _handle_chat_message(), _handle_system_message()
      bot_admin.py       ← admin panel, voice opts, RAG settings
      bot_users.py       ← notes CRUD, registration helpers
    features/            ← domain features: voice, calendar, documents, email
      bot_voice.py       ← voice pipeline: STT → LLM → TTS
      bot_calendar.py    ← calendar CRUD + LLM date parsing
      bot_documents.py   ← document upload, chunking, RAG index
    security/            ← auth, injection guard, security preamble
    ui/                  ← Screen DSL (bot_ui.py, bot_actions.py, render_telegram.py)
    screens/             ← YAML screen definitions (profile.yaml, main_menu.yaml, ...)
    store/               ← storage adapters (store_sqlite.py, store_base.py)
    setup/               ← shell scripts (run once on target: setup_voice.sh, etc.)
    services/            ← systemd .service files (taris-telegram, taris-web, ...)
    tests/               ← regression tests
      test_voice_regression.py   ← T01–T59 voice/config/LLM tests
      ui/test_ui.py              ← Playwright end-to-end Web UI tests
      llm/                       ← LLM provider unit tests
    telegram_menu_bot.py ← main entry point: bot.polling(), handle_callback()
    bot_web.py           ← FastAPI web server (Telegram-independent)
  doc/                   ← architecture, guides, protocols
  concept/               ← research, RAG architecture proposals
  .github/               ← Copilot instructions, skills, prompts
```

**Key invariant:** `~/.taris/` is **NOT symlinked** to `src/`. Always run the sync commands after editing — silent drift causes subtle bugs.

---

## 4. Daily Development Workflow

```
1. Edit source in  sintaris-pl/src/
2. Run tests locally  (PYTHONPATH=src python3 src/tests/test_voice_regression.py)
3. Sync to TARIS_HOME  (cp or pscp)
4. Restart services  (systemctl --user restart)
5. Verify in journal  (journalctl --user -u taris-telegram -n 10)
6. Commit & push  (git add … && git commit && git push)
7. Deploy to production  (only after tests pass on engineering target)
```

### Watching logs live

```bash
# OpenClaw (TariStation2) — local
journalctl --user -u taris-telegram -f

# PicoClaw (PI2) — remote
ssh stas@OpenClawPI2 "journalctl -u taris-telegram -f --no-pager"
```

### Expected startup log

```
[INFO] Taris BOT v2026.3.30+5
[INFO] DEVICE_VARIANT = openclaw
[INFO] LLM_PROVIDER   = ollama
[INFO] STT_PROVIDER   = faster_whisper
[INFO] Polling Telegram…
```

If `Polling Telegram…` is missing — look at the lines above for import errors or DB failures.

---

## 5. Writing Features — Step-by-Step

### 5.1 Adding a new command / menu item

1. **Handler function** in the relevant `src/telegram/*.py` or `src/features/*.py`:
   ```python
   def _handle_my_feature(chat_id: int) -> None:
       if not _is_allowed(chat_id): return _deny(chat_id)
       bot.send_message(chat_id, _t(chat_id, "my_feature_text"),
                        reply_markup=_back_keyboard())
   ```

2. **Add button** in the relevant `_keyboard()` builder in `bot_admin.py` or `bot_access.py`.

3. **Dispatch** in `handle_callback()` inside `telegram_menu_bot.py`:
   ```python
   elif data == "my_feature":
       if not _is_allowed(chat_id): return _deny(chat_id)
       _handle_my_feature(chat_id)
   ```

4. **i18n strings** in `src/strings.json` for `ru`, `en`, `de` (see §12).

5. **Web UI mirror**: apply the same feature to `src/bot_web.py` + `src/web/templates/` if it's a user-visible function (see §5.5).

6. **Test** — add a regression test (see §7).

### 5.2 Adding a multi-step input flow

```python
_pending_myflow: dict[int, dict] = {}   # global

def _start_myflow(chat_id):
    _pending_myflow[chat_id] = {"step": "name"}
    bot.send_message(chat_id, "Enter name:")

def _finish_myflow(chat_id, text):
    state = _pending_myflow.pop(chat_id, {})
    step = state.get("step")
    if step == "name":
        # process and confirm
        ...

# In handle_message() — BEFORE routing to chat/LLM:
if chat_id in _pending_myflow:
    return _finish_myflow(chat_id, text)
```

### 5.3 Adding a voice option toggle

See [dev-patterns.md §1](dev-patterns.md) for the 6-step pattern.

Key rules:
- All voice opts default to `False` in `_VOICE_OPTS_DEFAULTS`
- Opts are persisted to `~/.taris/voice_opts.json`
- On OpenClaw: check `DEVICE_VARIANT` to hide opts not applicable on the current platform

### 5.4 Adding an LLM call

**Single-turn (no history)** — for admin commands or structured extraction:
```python
from core.bot_llm import ask_llm
response = ask_llm(prompt, timeout=30, use_case="admin")
```

**Multi-turn (with conversation history)** — for chat and voice:
```python
from core.bot_llm import ask_llm_with_history
from core.bot_state import get_history_with_ids, add_to_history
from telegram.bot_access import _build_system_message, _user_turn_content

system_content = _build_system_message(chat_id, user_text)
history_entries = get_history_with_ids(chat_id)
history_msgs = [{"role": m["role"], "content": m["content"]} for m in history_entries]
current_content = _user_turn_content(chat_id, user_text)

messages = [{"role": "system", "content": system_content}] + history_msgs + [{"role": "user", "content": current_content}]

add_to_history(chat_id, "user", user_text)
response = ask_llm_with_history(messages, timeout=60, use_case="chat")
add_to_history(chat_id, "assistant", response)
```

**Never call LLM directly** — always use `ask_llm()` or `ask_llm_with_history()` from `bot_llm.py`. These handle provider routing, fallback, timeout, and logging.

### 5.5 Dual-channel UI rule

Every user-visible feature must work in **both** Telegram and Web UI:

| Telegram side | Web UI side |
|---|---|
| `src/telegram/bot_handlers.py` | `src/bot_web.py` (route handler) |
| `src/telegram/bot_admin.py` | `src/web/templates/*.html` |
| `src/screens/*.yaml` (Screen DSL) | Jinja2 template equivalent |
| `src/strings.json` | same `strings.json` via `_t()` |

### 5.6 Platform-conditional code

Use `DEVICE_VARIANT` constant from `bot_config.py`:

```python
from core.bot_config import DEVICE_VARIANT

if DEVICE_VARIANT == "openclaw":
    # OpenClaw-specific behaviour
elif DEVICE_VARIANT == "picoclaw":
    # PicoClaw-specific behaviour
```

Never use `platform.system()` or hostname checks. All variant switching goes through `DEVICE_VARIANT`.

For features unavailable on a platform, return an early `_t(chat_id, "feature_not_available")` or add a SKIP condition in voice opts menu.

---

## 6. Debugging

### 6.1 Reading logs

```bash
# Live stream — OpenClaw (local):
journalctl --user -u taris-telegram -f

# Last 50 lines — PicoClaw:
ssh stas@OpenClawPI2 "journalctl -u taris-telegram -n 50 --no-pager"

# Filter by component:
journalctl --user -u taris-telegram -n 200 --no-pager | grep "\[Voice\]\|\[LLM\]\|\[History\]"
```

**Key log prefixes to watch:**

| Prefix | Module | What it logs |
|---|---|---|
| `[Voice]` | `bot_voice.py` | STT/LLM/TTS timings, pipeline stages |
| `[STT]` | `bot_voice.py` | provider, language, result |
| `[LLM]` | `bot_llm.py` | provider, latency, token counts |
| `[History]` | `bot_state.py` | history load/save |
| `[RAG]` | `bot_access.py` | FTS hits, chunks injected |
| `[Security]` | `bot_security.py` | injection blocks, access denials |
| `[Chat]` | `bot_handlers.py` | multi-turn message sizes |

### 6.2 Common import errors on startup

```
ImportError: cannot import name 'X' from 'telegram.bot_access'
```
→ You added a function but didn't export it, or there's a circular import. Check that the function is defined at module level (not inside another function) and that the import chain doesn't loop.

```
ModuleNotFoundError: No module named 'core.bot_config'
```
→ Run from the repo root with `PYTHONPATH=src`. Or: you deployed the file to the wrong path under `~/.taris/`.

### 6.3 LLM not responding

Check:
1. `LLM_PROVIDER` in `~/.taris/bot.env` — is it set correctly?
2. For Ollama: `systemctl --user status ollama` — is it running?
3. For OpenAI: `OPENAI_API_KEY` set? Try `curl https://api.openai.com/v1/models -H "Authorization: Bearer $OPENAI_API_KEY"`.
4. Add `log.debug()` calls in the LLM call path and check the journal.

### 6.4 Voice message not transcribed

```bash
journalctl --user -u taris-telegram -n 30 | grep -E "STT|VAD|voice|ogg"
```

Check order:
1. `[Voice] Download` — OGG received from Telegram
2. `[Voice] Convert` — ffmpeg decodes OGG → PCM
3. `[STT]` line — provider + language + text
4. `[Voice] LLM call start` — goes to LLM with `history=N`

If step 3 is missing → STT provider not responding or audio was rejected by VAD. Look for `VAD filter removed` with `100%`.

### 6.5 History not working

Check: `[Voice] LLM call start: ... history=0` → history is empty.

Reasons:
- History clear was called (`clear_history`)
- Service was restarted and history not persisted to DB (check `_DB_HISTORY_ENABLED` in `bot_state.py`)
- `add_to_history()` not called after LLM response

### 6.6 Web UI not updating after deploy

The browser caches old HTML/JS aggressively. Hard refresh: `Ctrl+Shift+R` (or `Cmd+Shift+R`). If still stale, check the `Cache-Control: no-store` header is present (set via `meta` tags in `base.html`).

### 6.7 Debugging with `--verbose` tests

```bash
PYTHONPATH=src python3 src/tests/test_voice_regression.py --verbose --test t_voice_history_context
```

This prints which assertions pass/fail with full detail.

---

### 6.8 IDE Debugger Attach (VS Code / PyCharm / Eclipse)

Taris runs as a standard Python process, so any IDE that supports Python remote debugging
can attach to it. The two recommended approaches are:

1. **Launch mode** — stop the systemd service, launch the bot directly from your IDE.
   Full breakpoints, step-through, variable inspection. Best for local OpenClaw development.
2. **Attach mode** — connect your IDE to the running service process via `debugpy`.
   The service keeps running; you attach on demand. Best for investigating live issues.

> **PicoClaw note:** Connect your IDE via VS Code Remote-SSH to the Pi first, then
> open the repository and use the same launch configs below, substituting paths with
> `/home/stas/.taris/` and the Pi host.

---

#### Prerequisite — install debugpy

```bash
# On TariStation2 (OpenClaw — local):
pip install debugpy

# On PicoClaw via SSH:
ssh stas@OpenClawPI2 "pip3 install debugpy"
```

---

#### Option A — Launch from VS Code (stop service, full debug)

Create `.vscode/launch.json` in the project root:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Taris — OpenClaw (launch)",
      "type": "debugpy",
      "request": "launch",
      "program": "${workspaceFolder}/src/telegram_menu_bot.py",
      "python": "/usr/bin/python3",
      "cwd": "${workspaceFolder}/src",
      "env": {
        "PYTHONPATH": "${workspaceFolder}/src",
        "DEVICE_VARIANT": "openclaw",
        "PYTHONUNBUFFERED": "1"
      },
      "envFile": "/home/stas/.taris/bot.env",
      "console": "integratedTerminal",
      "justMyCode": false
    },
    {
      "name": "Taris — OpenClaw (attach by port)",
      "type": "debugpy",
      "request": "attach",
      "connect": { "host": "127.0.0.1", "port": 5678 },
      "pathMappings": [
        {
          "localRoot": "${workspaceFolder}/src",
          "remoteRoot": "/home/stas/.taris"
        }
      ],
      "justMyCode": false
    },
    {
      "name": "Taris — PicoClaw (remote SSH attach)",
      "type": "debugpy",
      "request": "attach",
      "connect": { "host": "OpenClawPI2", "port": 5678 },
      "pathMappings": [
        {
          "localRoot": "${workspaceFolder}/src",
          "remoteRoot": "/home/stas/.taris"
        }
      ],
      "justMyCode": false
    }
  ]
}
```

> **`envFile`**: VS Code reads the file as `KEY=VALUE` lines (same format as `bot.env`).
> This loads `BOT_TOKEN` and `ALLOWED_USERS` into the launched process exactly as systemd does.

**Steps for launch mode:**

```bash
# 1. Stop the service so only one bot process polls Telegram (otherwise 409 conflict)
systemctl --user stop taris-telegram taris-web

# 2. Open VS Code, open Run and Debug (Ctrl+Shift+D)
# 3. Select "Taris — OpenClaw (launch)" and press F5
# 4. Set breakpoints in any src/ file — they work immediately
```

---

#### Option B — Attach to running service (debugpy listen)

This keeps the service running normally; you inject breakpoints on demand.

**Step 1** — add a debug listener to the bot startup (temporary, remove before commit):

```python
# At the very top of src/telegram_menu_bot.py (below the imports)
import debugpy
debugpy.listen(("127.0.0.1", 5678))
# debugpy.wait_for_client()  # uncomment to pause startup until IDE connects
```

**Step 2** — sync and restart:

```bash
cp src/telegram_menu_bot.py ~/.taris/
systemctl --user restart taris-telegram
```

**Step 3** — in VS Code, select **"Taris — OpenClaw (attach by port)"** and press F5.
The debugger connects. You can now set breakpoints in any `src/` file.

**Step 4** — remove `debugpy.listen()` before committing.

> **Port forwarding for PicoClaw:** If attaching to a Pi, open an SSH tunnel first:
> ```bash
> ssh -L 5678:127.0.0.1:5678 stas@OpenClawPI2
> ```
> Then use the **"attach by port"** config on `127.0.0.1:5678`.

---

#### Option C — PyCharm / IntelliJ remote debug

PyCharm uses `pydevd` (included in the PyCharm helpers) instead of `debugpy`.

**Step 1** — in PyCharm, create a **Python Debug Server** run configuration:
- `Settings > Run > Edit Configurations > + > Python Debug Server`
- IDE host: `localhost`, Port: `12345`
- Note the code snippet PyCharm shows you — it looks like:
  ```python
  import pydevd_pycharm
  pydevd_pycharm.settrace('localhost', port=12345, stdoutToServer=True, stderrToServer=True)
  ```

**Step 2** — paste the snippet into `src/telegram_menu_bot.py` (temporarily, after imports).

**Step 3** — start the Debug Server in PyCharm first, then restart the service:

```bash
cp src/telegram_menu_bot.py ~/.taris/
systemctl --user restart taris-telegram
```

PyCharm connects automatically as the bot starts.

**For PicoClaw** — install `pydevd-pycharm` on the Pi (`pip3 install pydevd-pycharm`) and
use your workstation IP instead of `localhost` in `settrace()`.

---

#### Option D — Eclipse / PyDev

Eclipse with the PyDev plugin uses the same `pydevd` protocol as PyCharm.

**Step 1** — in Eclipse, open `PyDev > Start Debug Server` (port 5678 by default).

**Step 2** — add to `src/telegram_menu_bot.py` (temporarily):

```python
import pydevd
pydevd.settrace('localhost', port=5678, stdoutToServer=True, stderrToServer=True)
```

**Step 3** — sync and restart the service. Eclipse connects when the bot starts.

Install PyDev helper on the target if needed:
```bash
pip3 install pydevd
```

---

#### Breakpoint tips

| Scenario | Recommendation |
|---|---|
| Debugging a Telegram callback | Set breakpoint in `handle_callback()` in `telegram_menu_bot.py` |
| Debugging LLM call / context | Breakpoint in `bot_handlers.py:_run()` or `bot_voice.py` LLM block |
| Debugging RAG retrieval | Breakpoint in `bot_access.py:_docs_rag_context()` |
| Debugging voice pipeline | Breakpoint in `bot_voice.py:_process_voice_message()` |
| Inspecting history at call time | Breakpoint after `get_history_with_ids(chat_id)` in handlers |

**Inspecting LLM call context at runtime:**

```python
# Paste in debug console (VS Code / PyCharm Evaluate Expression):
import json
print(json.dumps([{"role": m["role"], "content": m["content"][:80]} for m in messages], ensure_ascii=False, indent=2))
```

This shows exactly what history + system message was sent to the LLM — the same data now
logged automatically to `llm_calls.context_snapshot` in the DB.

---

#### Common pitfalls

| Problem | Fix |
|---|---|
| `409 Conflict` on Telegram after launch | Service still running — `systemctl --user stop taris-telegram` first |
| `BOT_TOKEN not set` when launching from IDE | Add `"envFile": "/home/stas/.taris/bot.env"` to launch config |
| Breakpoints not hit (grayed out) | Set `"justMyCode": false`; ensure `pathMappings` match deployed paths |
| `debugpy` port busy | `lsof -i:5678` to find PID, `kill <PID>` |
| Import errors in IDE | Add `"PYTHONPATH": "src"` env var in launch config |

---

## 7. Testing

### 7.1 Test categories

| Category | Where | Run command | When to run |
|---|---|---|---|
| Voice regression (T01–T59) | `src/tests/test_voice_regression.py` | `PYTHONPATH=src python3 src/tests/test_voice_regression.py` | After any `bot_voice.py`, `bot_access.py`, `bot_config.py`, `strings.json` change |
| Web UI Playwright | `src/tests/ui/test_ui.py` | `pytest src/tests/ui/test_ui.py -v` | After `bot_web.py` or template change |
| LLM unit tests | `src/tests/llm/` | `pytest src/tests/llm/` | After `bot_llm.py` change |
| Smoke test | Journal grep | `journalctl -u taris-telegram -n 20` | After every deploy |

Full test reference → [test-suite.md](test-suite.md)

### 7.2 Running a single test

```bash
PYTHONPATH=src python3 src/tests/test_voice_regression.py --test t_voice_history_context
PYTHONPATH=src python3 src/tests/test_voice_regression.py --test t_rag_pipeline_completeness
```

### 7.3 Mandatory: add a regression test for every bug fix

For every bug you fix, add a test that would have caught it **before** the fix:

```python
def t_my_bug_fix(**_) -> list[TestResult]:
    """T60 — <description of what was broken and what the fix asserts>."""
    results = []
    t0 = time.time()

    try:
        src = Path("src/features/bot_voice.py").read_text()
        ok = "ask_llm_with_history" in src   # the invariant that must hold
        results.append(TestResult(
            "my_check_name", "PASS" if ok else "FAIL", time.time() - t0,
            "description of what was found",
        ))
    except Exception as e:
        results.append(TestResult("my_check_name", "FAIL", time.time() - t0, str(e)))

    return results
```

Then add the function to the `TEST_FUNCTIONS` list at the bottom of the file.

**Test ID convention:**
- T01–T21: voice pipeline, models, i18n
- T22–T26: SQLite, RAG, web links, system chat
- T27–T31: OpenClaw-specific (faster-whisper, Ollama, routing)
- T32–T50: feature regression (pipeline logger, STT fallback, LLM routing, voice admin)
- T51–T59: §22 notes, §4 RAG pipeline, §9.1 history context

Use the next sequential T number. Document in [test-suite.md](test-suite.md) in the same commit.

### 7.4 Test design rules

- **Use source inspection** (`Path("src/...").read_text()`) not live imports — the test runner adds `~/.taris/` to `sys.path` early, so dynamic imports would pick up the deployed version
- **Add SKIP guards** for optional components (`if DEVICE_VARIANT != "openclaw": return SKIP`)
- **FAIL** blocks deployment; **WARN** (>30% slower than baseline) → investigate; **SKIP** is OK for absent optional features

### 7.5 Running the full Playwright suite

```bash
# Ensure the Web UI is running on TariStation2
systemctl --user status taris-web

# Run all UI tests
cd ~/projects/sintaris-pl
pytest src/tests/ui/test_ui.py -v --base-url http://localhost:8080 --browser chromium

# Create test users if needed (conftest.py handles this automatically)
```

---

## 8. Deployment

### 8.1 OpenClaw (TariStation2 → TariStation1)

**TariStation2 (engineering, local cp):**

```bash
# Sync all commonly-changed files:
cp ~/projects/sintaris-pl/src/core/bot_config.py   ~/.taris/core/
cp ~/projects/sintaris-pl/src/core/bot_llm.py      ~/.taris/core/
cp ~/projects/sintaris-pl/src/telegram/bot_access.py ~/.taris/telegram/
cp ~/projects/sintaris-pl/src/features/bot_voice.py ~/.taris/features/
cp ~/projects/sintaris-pl/src/bot_web.py            ~/.taris/
cp ~/projects/sintaris-pl/src/web/templates/*.html  ~/.taris/web/templates/
cp ~/projects/sintaris-pl/src/strings.json          ~/.taris/

systemctl --user restart taris-telegram taris-web
sleep 3
journalctl --user -u taris-telegram -n 8 --no-pager | grep -E "Version|Polling|ERROR"
```

**TariStation1 / SintAItion (production, SSH — requires explicit owner confirmation):**

```bash
source ~/projects/sintaris-pl/.env
sshpass -p "$OPENCLAW1PWD" scp -o StrictHostKeyChecking=no \
  src/features/bot_voice.py \
  stas@SintAItion:/home/stas/.taris/features/

sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no stas@SintAItion \
  "systemctl --user restart taris-telegram && sleep 3 && journalctl --user -u taris-telegram -n 8 --no-pager"
```

Skill: `/taris-deploy-openclaw-target`

### 8.2 PicoClaw (OpenClawPI2 → OpenClawPI)

**OpenClawPI2 (engineering, SCP + SSH):**

```bash
# Linux/Mac:
scp src/features/bot_voice.py  stas@OpenClawPI2:/home/stas/.taris/features/
scp src/strings.json           stas@OpenClawPI2:/home/stas/.taris/
ssh stas@OpenClawPI2 "sudo systemctl restart taris-telegram && sleep 3 && sudo journalctl -u taris-telegram -n 10 --no-pager"
```

**OpenClawPI (production, master branch only):**

```bash
# Deploy ONLY from master branch after PI2 tests pass
git checkout master
git merge <feature-branch>
git push
scp src/features/bot_voice.py  stas@OpenClawPI:/home/stas/.taris/features/
ssh stas@OpenClawPI "sudo systemctl restart taris-telegram"
```

Skill: `/taris-deploy-to-target`

### 8.3 Service file changes

Service files live in `src/services/`. When you change them:

```bash
# OpenClaw
cp src/services/taris-telegram.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user restart taris-telegram

# PicoClaw (remote)
scp src/services/taris-telegram.service stas@OpenClawPI2:/tmp/
ssh stas@OpenClawPI2 "sudo cp /tmp/taris-telegram.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl restart taris-telegram"
```

### 8.4 Schema / migration changes

Use the `/taris-deploy-to-target` skill's 9-step safe update protocol when changing `bot_db.py` or `store_sqlite.py`. **Always backup first.**

```bash
# Backup before migration (OpenClaw local):
cp -r ~/.taris/taris.db ~/.taris/taris.db.backup-$(date +%Y%m%d)
```

---

## 9. Platform-Specific Behaviour

### 9.1 OpenClaw-specific components

| Component | Config | Notes |
|---|---|---|
| faster-whisper STT | `STT_PROVIDER=faster_whisper` | Default on openclaw; SKIP tests on picoclaw |
| Ollama LLM | `LLM_PROVIDER=ollama`, `OLLAMA_URL=http://127.0.0.1:11434` | systemd user service |
| GPU acceleration | `FASTER_WHISPER_DEVICE=cuda` or `rocm` | AMD: needs ROCm; NVIDIA: CUDA |
| REST API `/api/*` | `TARIS_API_TOKEN=<token>` | Bearer auth; consumed by sintaris-openclaw |
| sintaris-openclaw | Port `:18789` | Skills gateway; not part of this repo |

**Testing OpenClaw-specific features:**

```bash
DEVICE_VARIANT=openclaw PYTHONPATH=src python3 src/tests/test_voice_regression.py \
  --test t_openclaw_stt_routing --test t_openclaw_ollama_provider
```

### 9.2 PicoClaw-specific components

| Component | Config | Notes |
|---|---|---|
| Vosk STT | `STT_PROVIDER=vosk`, `VOSK_MODEL_DIR=/home/stas/.taris/models/vosk-model-ru` | Default on picoclaw |
| Piper TTS | `PIPER_BIN=/usr/local/bin/piper`, `PIPER_MODEL=/home/stas/.taris/models/irina-low.onnx` | Required |
| taris binary LLM | `LLM_PROVIDER=taris`, `TARIS_BIN=/usr/local/bin/taris` | Routes to OpenRouter |
| tmpfs voice cache | `/dev/shm/piper/` (mount via setup script) | Reduces SD card writes |

**Testing PicoClaw STT models on PI2:**

```bash
ssh stas@OpenClawPI2 "cd ~/.taris && python3 tests/test_voice_regression.py --test t_model_files_present"
```

### 9.3 Variant detection in code

```python
from core.bot_config import DEVICE_VARIANT, STT_PROVIDER

# Skip block for wrong platform:
if DEVICE_VARIANT != "openclaw":
    return [TestResult("my_test", "SKIP", 0.0, "openclaw only")]

# Feature gate in handler:
if DEVICE_VARIANT == "picoclaw" and not Path(VOSK_MODEL_DIR).exists():
    return bot.send_message(chat_id, _t(chat_id, "vosk_model_missing"))
```

---

## 10. LLM Integration Patterns

### 10.1 Provider routing

All LLM calls go through `ask_llm()` or `ask_llm_with_history()` in `bot_llm.py`. The actual provider is selected via:

```
LLM_PROVIDER=ollama        → _ask_ollama()      (Ollama local — openclaw default)
LLM_PROVIDER=openai        → _ask_openai()      (OpenAI API)
LLM_PROVIDER=taris         → _ask_taris()       (taris binary → OpenRouter)
LLM_PROVIDER=local         → _ask_local()       (llama.cpp direct)
LLM_PROVIDER=openclaw      → _ask_openclaw()    (sintaris-openclaw gateway)
```

Fallback: if primary provider fails and `LLM_FALLBACK_PROVIDER` is set, `_ask_with_fallback()` retries automatically.

### 10.2 Adding a new LLM provider

1. Add constants to `bot_config.py`:
   ```python
   MYPROVIDER_URL   = os.environ.get("MYPROVIDER_URL",   "https://api.example.com")
   MYPROVIDER_MODEL = os.environ.get("MYPROVIDER_MODEL", "my-model-name")
   MYPROVIDER_KEY   = os.environ.get("MYPROVIDER_KEY",   "")
   ```

2. Add function in `bot_llm.py`:
   ```python
   def _ask_myprovider(prompt: str, timeout: int = 30) -> str:
       import requests
       resp = requests.post(MYPROVIDER_URL, json={...}, timeout=timeout)
       return resp.json()["choices"][0]["message"]["content"].strip()
   ```

3. Register in `_DISPATCH` dict:
   ```python
   _DISPATCH = { ..., "myprovider": _ask_myprovider }
   ```

4. Set in `bot.env`:
   ```bash
   LLM_PROVIDER=myprovider
   ```

5. Add T-numbered regression test verifying the provider constant and dispatch entry exist.

### 10.3 Conversation history internals

History is stored in `bot_state.py`:
- Short-term: in-memory `dict[int, list[dict]]` — survives restart if persisted to DB
- Mid-term: DB `conversation_history` table — last N turns
- Long-term: DB `memory` table — summarized older context

To clear history for a user:
```python
from core.bot_state import clear_history
clear_history(chat_id)
```

To inspect history count:
```python
from core.bot_state import get_history
print(len(get_history(chat_id)))
```

### 10.4 System prompt architecture

The system message is built by `_build_system_message(chat_id, user_text)` in `bot_access.py`:

```
[SECURITY PREAMBLE]     ← from security/bot_security.py SECURITY_PREAMBLE
[BOT CONFIG BLOCK]      ← version, LLM provider, STT lang, etc.
[MEMORY NOTE]           ← "You have access to conversation history…"
[LONG-TERM MEMORY]      ← get_memory_context(chat_id) if present
[LANGUAGE INSTRUCTION]  ← "Answer in Russian" etc.
```

The user turn is built by `_user_turn_content(chat_id, user_text)`:

```
[RAG CONTEXT]           ← FTS5 chunks from uploaded documents (if any match)
[WRAPPED USER TEXT]     ← _wrap_user_input(user_text)
```

---

## 11. Voice Pipeline Integration

### 11.1 Pipeline stages

```
Telegram voice msg
  → download OGG
  → ffmpeg decode → PCM
  → VAD filter (remove silence)
  → STT (Vosk / faster-whisper)
  → injection check
  → build messages (system + history + current)
  → LLM (ask_llm_with_history)
  → save turns to history
  → TTS (Piper → OGG)
  → send voice + text to user
```

### 11.2 Modifying STT

New STT providers follow the pattern in `bot_voice.py`:

```python
def _stt_myprovider(audio_bytes: bytes, lang: str = "ru") -> str:
    # process audio_bytes (PCM 16kHz S16LE), return transcript string
    ...

# In STT dispatch block:
elif STT_PROVIDER == "myprovider":
    transcript = _stt_myprovider(pcm_data, lang=_stt_lang)
```

Add `MYPROVIDER_MODEL` constant to `bot_config.py`. Add a T-numbered regression test.

### 11.3 TTS integration

TTS is handled by `_tts_to_ogg(text, lang="ru") -> Optional[bytes]` in `bot_voice.py`. It calls Piper via subprocess. To add a TTS engine:

```python
def _tts_myprovider(text: str, lang: str) -> Optional[bytes]:
    # return OGG bytes or None on failure
    ...

# In _tts_to_ogg():
if TTS_PROVIDER == "myprovider":
    return _tts_myprovider(text, lang)
```

Add `TTS_PROVIDER` constant to `bot_config.py`.

### 11.4 STT language routing

STT language is controlled by `STT_LANG` (env-var), not the Telegram UI language:

```python
# Always use _stt_lang (= STT_LANG env), not _lang(chat_id):
transcript = _stt_vosk(pcm_data, lang=_stt_lang)
```

TTS language follows the user's UI language (`_voice_lang(chat_id)`).

---

## 12. i18n / Strings

**All user-visible text** must be in `src/strings.json`. Never hardcode Russian, German, or English text in `.py` files.

```json
{
  "ru": { "my_key": "Текст на русском" },
  "en": { "my_key": "Text in English" },
  "de": { "my_key": "Text auf Deutsch" }
}
```

Usage in Python:

```python
_t(chat_id, "my_key")                   # language resolved from user registration
_t(chat_id, "my_key", value=42)         # with format kwargs
_t(chat_id, "my_key", name="Taris")
```

**Validation:** `PYTHONPATH=src python3 src/tests/test_voice_regression.py --test t_i18n_string_coverage` checks that all 3 languages have the same key set with no empty values.

**Current key count:** ~330 keys per language (as of v2026.3.30+5).

---

## 13. Release Process

```
1. Edit src/  →  2. Test locally  →  3. Deploy to TariStation2/PI2  →  4. Verify journal
   →  5. Bump version  →  6. Commit  →  7. Push  →  8. Deploy prod (with confirmation)
```

### Version bump (always 2 files)

```python
# src/core/bot_config.py
BOT_VERSION = "2026.3.31"   # YYYY.M.D, no zero-padding
```

```json
// src/release_notes.json — prepend at top, never append
[
  {
    "version": "2026.3.31",
    "date":    "2026-03-31",
    "title":   "Short feature name",
    "notes":   "- Bullet 1\n- Bullet 2"
  },
  ...
]
```

**Never use `\_` in JSON notes strings** (invalid JSON escape). Use `_` without backslash.

Validate:

```bash
python3 -c "import json; json.load(open('src/release_notes.json')); print('OK')"
python3 -c "import json; json.load(open('src/strings.json')); print('OK')"
```

### Commit message conventions

```
feat: add X (vY.Y.Y)
fix: description (vY.Y.Y)
test: T59 regression for X
docs: update dev-guide / architecture
chore: bump version to Y.Y.Y
```

Always add:
```
Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```

### Vibe coding protocol

After every completed Copilot session, append a row to `doc/vibe-coding-protocol.md`:

```
| HH:MM UTC | Start | End | Duration | Description | Steps | Complexity | Turns | Model | Files | Status |
```

---

## 14. Common Pitfalls

| Pitfall | Symptom | Fix |
|---|---|---|
| Deployed `~/.taris/` not updated | Code change has no effect | Run sync commands; check `diff src/x.py ~/.taris/x.py` |
| `\_` in release_notes.json | JSON parse error on startup | Replace `\_` with `_` |
| Missing `ru`/`en`/`de` in strings.json | T13 FAIL; KeyError at runtime | Add all 3 languages; run `t_i18n_string_coverage` |
| LLM called without history | Bot forgets conversation context | Use `ask_llm_with_history(messages)`, not `ask_llm(prompt)` |
| Importing deployed module in tests | Test passes but wrong file checked | Use `Path("src/...").read_text()` source inspection |
| Wrong sys.path in PYTHONPATH | `ModuleNotFoundError` in tests | Always `PYTHONPATH=src python3 src/tests/…` |
| Service file not reloaded | `systemctl restart` uses old unit | `daemon-reload` after any `.service` file change |
| Feature only in Telegram | Web UI missing button/route | Apply change to `bot_web.py` + template in same commit |
| PI1 receives non-master branch | Production out of sync | Always `git checkout master` before PI1 deploy |
| Voice opts defaults to `True` | Unexpected feature enabled on new install | All `_VOICE_OPTS_DEFAULTS` entries must be `False` |
| Hardcoded language string in `.py` | T55 FAIL; wrong language shown to users | Move to `strings.json`; use `_t(chat_id, key)` |
| ask_llm timeout 30s | LLM hangs the Telegram polling thread | Use `timeout=60-90` for chat/voice; use threading |
| Direct subprocess call | Inconsistent error handling, no logging | Always use `_run_subprocess([...], timeout=N)` |

---

## Quick Reference

| Task | Command |
|---|---|
| Run all tests | `PYTHONPATH=src python3 src/tests/test_voice_regression.py` |
| Run single test | `PYTHONPATH=src python3 … --test t_FUNCNAME` |
| Sync all to TariStation2 | `cp src/core/*.py ~/.taris/core/ && cp src/features/*.py ~/.taris/features/ && systemctl --user restart taris-telegram taris-web` |
| Watch live logs | `journalctl --user -u taris-telegram -f` |
| Check history in DB | `sqlite3 ~/.taris/taris.db "SELECT role, substr(content,1,80) FROM conversation_history ORDER BY id DESC LIMIT 10;"` |
| Validate JSON files | `python3 -c "import json; json.load(open('src/release_notes.json'))"` |
| Git status + diff | `git --no-pager status && git --no-pager diff --stat` |
| Bump version skill | `/taris-bump-version` |
| Deploy OpenClaw skill | `/taris-deploy-openclaw-target` |
| Deploy PicoClaw skill | `/taris-deploy-to-target` |
