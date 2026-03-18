# Task: Extract LLM Prompts & Centralise Config

**Version target:** v2026.3.34  
**Branch:** `copilot/refactor-prompts-llm`  
**Deploy target:** OpenClawPI2 (PI2) first, then PI1 after tests pass.

---

## Why

Every LLM prompt was hard-coded inline in the source files as f-strings or multi-line string literals. LLM tuning parameters (temperature, max_tokens, etc.) were also hard-coded. This makes it hard to:
- Tweak prompts without touching business logic
- See all prompts in one place without reading seven files
- A/B test prompt wording without a code deploy

---

## What Changed

### New files
| File | Purpose |
|---|---|
| `src/prompts.json` | All prompt templates keyed by domain. Single source of truth. |
| `src/core/bot_prompts.py` | Loader: reads `prompts.json` once at import, exposes `PROMPTS: dict` and `fmt_prompt(template, **kwargs)` helper. |

### Modified files
| File | Change |
|---|---|
| `src/core/bot_config.py` | Version → `2026.3.34`; 5 new LLM tuning constants (`YANDEXGPT_TEMPERATURE`, `YANDEXGPT_MAX_TOKENS`, `ANTHROPIC_MAX_TOKENS`, `LOCAL_MAX_TOKENS`, `LOCAL_TEMPERATURE`) |
| `src/core/bot_llm.py` | Import 5 new constants; replace 6 hard-coded param literals |
| `src/security/bot_security.py` | `SECURITY_PREAMBLE` loaded from `PROMPTS["security_preamble"]` |
| `src/telegram/bot_access.py` | `_LANG_INSTRUCTION` dict + STT hints loaded from `PROMPTS` |
| `src/telegram/bot_handlers.py` | `_SYSTEM_PROMPT` loaded from `PROMPTS["system_prompt"]` |
| `src/features/bot_mail_creds.py` | Digest header loaded from `PROMPTS["mail"]["digest_header"]` |
| `src/features/bot_calendar.py` | 4 prompt templates loaded from `PROMPTS["calendar"][*]` |
| `src/bot_web.py` | 2 prompt templates loaded from `PROMPTS["web"][*]` |
| `src/release_notes.json` | Prepend v2026.3.34 entry |

---

## `fmt_prompt` Convention

Templates in `prompts.json` use `{placeholder}` syntax (Python identifier names only).
The helper `fmt_prompt(template, **kwargs)` uses a regex `\{[A-Za-z_][A-Za-z0-9_]*\}` to substitute
placeholders, which means:
- `{now_iso}`, `{text}`, `{events_hint}`, `{bot_name}` → substituted
- `{"events": []}` (JSON literal braces in prompt output spec) → left untouched ✅
- User-provided text containing `{arbitrary}` → left untouched ✅ (regex won't match non-identifier patterns)

---

## prompts.json Structure

```
prompts.json
├── security_preamble          ← used in bot_security.py
├── lang_instructions
│   ├── ru
│   ├── de
│   └── en
├── stt_hints
│   ├── ru
│   ├── de
│   └── en
├── system_prompt              ← used in bot_handlers.py
├── calendar
│   ├── event_parse            ← _finish_cal_add  placeholders: {now_iso} {text}
│   ├── date_range             ← _handle_calendar_query  {now_iso} {text}
│   ├── intent                 ← _handle_cal_console  {now_iso} {events_hint} {text}
│   └── edit_dt                ← _cal_handle_edit_input  {now_iso} {text}
├── mail
│   └── digest_header          ← _build_digest_prompt (prefix string)
└── web
    ├── cal_event_parse        ← _cal_parse_events_from_text  {now_iso} {text}
    └── cal_intent             ← calendar_console_route  {now_iso} {events_hint} {text}
```

---

## Detailed Step-by-Step

### Step 1 — `src/prompts.json` ✅ DONE
- Created with all 12 template keys above
- Uses **literal** `{` `}` for JSON examples in prompt output specs — NOT `{{`/`}}` Python escaping
- Uses `{identifier}` for `fmt_prompt` placeholders

### Step 2 — `src/core/bot_prompts.py` ✅ DONE  
- Reads `prompts.json` once at import, exposes `PROMPTS: dict`
- Must add `fmt_prompt(template: str, **kwargs) -> str` helper (regex substitution)

### Step 3 — `src/core/bot_config.py` ✅ DONE
- Version bumped to `"2026.3.34"`
- Added after `OPENAI_BASE_URL` line:
  ```python
  YANDEXGPT_TEMPERATURE  = float(os.getenv("YANDEXGPT_TEMPERATURE", "0.6"))
  YANDEXGPT_MAX_TOKENS   = os.getenv("YANDEXGPT_MAX_TOKENS", "2000")
  ANTHROPIC_MAX_TOKENS   = int(os.getenv("ANTHROPIC_MAX_TOKENS", "1024"))
  LOCAL_MAX_TOKENS       = int(os.getenv("LOCAL_MAX_TOKENS", "512"))
  LOCAL_TEMPERATURE      = float(os.getenv("LOCAL_TEMPERATURE", "0.7"))
  ```

### Step 4 — `src/core/bot_llm.py` ✅ DONE
**Import additions** — add to `from core.bot_config import (...)`:
```python
YANDEXGPT_TEMPERATURE, YANDEXGPT_MAX_TOKENS,
ANTHROPIC_MAX_TOKENS, LOCAL_MAX_TOKENS, LOCAL_TEMPERATURE,
```
**Replacement sites** (6 occurrences):
- `_ask_yandexgpt`: `"temperature": 0.6, "maxTokens": "2000"` → `"temperature": YANDEXGPT_TEMPERATURE, "maxTokens": YANDEXGPT_MAX_TOKENS`
- `_ask_anthropic`: `"max_tokens": 1024` → `"max_tokens": ANTHROPIC_MAX_TOKENS`
- `_ask_local`: `"max_tokens": 512, "temperature": 0.7` → `"max_tokens": LOCAL_MAX_TOKENS, "temperature": LOCAL_TEMPERATURE`
- History-aware versions at lines ~308, ~316, ~339, ~385 — same replacements

### Step 5 — `src/security/bot_security.py` ✅ DONE
```python
# ADD after existing imports:
from core.bot_prompts import PROMPTS, fmt_prompt

# REPLACE SECURITY_PREAMBLE definition:
SECURITY_PREAMBLE = fmt_prompt(PROMPTS["security_preamble"], bot_name=BOT_NAME)
```

### Step 6 — `src/telegram/bot_access.py` ✅ DONE
```python
# ADD after existing imports:
from core.bot_prompts import PROMPTS, fmt_prompt

# REPLACE _LANG_INSTRUCTION dict:
_LANG_INSTRUCTION: dict[str, str] = PROMPTS["lang_instructions"]

# In _with_lang_voice(), REPLACE stt_hint ternary with:
stt_hint = PROMPTS["stt_hints"].get(lang, PROMPTS["stt_hints"]["en"])
```

### Step 7 — `src/telegram/bot_handlers.py` ✅ DONE
```python
# ADD after existing imports:
from core.bot_prompts import PROMPTS

# REPLACE _SYSTEM_PROMPT:
_SYSTEM_PROMPT = PROMPTS["system_prompt"]
```

### Step 8 — `src/features/bot_mail_creds.py` ✅ DONE
```python
# ADD after existing imports:
from core.bot_prompts import PROMPTS

# In _build_digest_prompt(), REPLACE hardcoded prefix with:
return (
    PROMPTS["mail"]["digest_header"]
    + "\n\n".join(sections)
)
```

### Step 9 — `src/features/bot_calendar.py` ✅ DONE
```python
# ADD after existing imports:
from core.bot_prompts import PROMPTS, fmt_prompt

# 4 replacement sites:
# 1. _finish_cal_add:
prompt = fmt_prompt(PROMPTS["calendar"]["event_parse"], now_iso=now_iso, text=text)

# 2. _handle_calendar_query:
prompt = fmt_prompt(PROMPTS["calendar"]["date_range"], now_iso=now_iso, text=text)

# 3. _handle_cal_console:
prompt = fmt_prompt(PROMPTS["calendar"]["intent"], now_iso=now_iso, events_hint=events_hint, text=text)

# 4. _cal_handle_edit_input (field=="dt"):
prompt = fmt_prompt(PROMPTS["calendar"]["edit_dt"], now_iso=now_iso, text=text)
```

### Step 10 — `src/bot_web.py` ✅ DONE
```python
# ADD to existing imports:
from core.bot_prompts import PROMPTS, fmt_prompt

# 2 replacement sites:
# 1. _cal_parse_events_from_text:
prompt = fmt_prompt(PROMPTS["web"]["cal_event_parse"], now_iso=now_iso, text=text)

# 2. calendar_console_route (intent_prompt):
intent_prompt = fmt_prompt(PROMPTS["web"]["cal_intent"], now_iso=now_iso, events_hint=events_hint, text=text)
```

### Step 11 — `src/release_notes.json` ✅ DONE
Prepend:
```json
{
  "version": "2026.3.34",
  "date": "2026-03-18",
  "title": "Prompt templates centralised + LLM params configurable",
  "notes": "- All LLM prompts extracted to src/prompts.json\n- New core/bot_prompts.py loader with fmt_prompt() helper\n- LLM tuning params (temperature, max_tokens) configurable via env vars\n- bot_config.py: YANDEXGPT_TEMPERATURE, YANDEXGPT_MAX_TOKENS, ANTHROPIC_MAX_TOKENS, LOCAL_MAX_TOKENS, LOCAL_TEMPERATURE"
}
```

---

## Deploy & Test Sequence

use my ...deploy-to-target skill for deplyment and testing

```bat
rem Step 12 — Deploy to PI2
pscp -pw "%HOSTPWD%" src\prompts.json stas@OpenClawPI2:/home/stas/.picoclaw/
pscp -pw "%HOSTPWD%" src\core\bot_config.py src\core\bot_llm.py src\core\bot_prompts.py stas@OpenClawPI2:/home/stas/.picoclaw/core/
pscp -pw "%HOSTPWD%" src\security\bot_security.py stas@OpenClawPI2:/home/stas/.picoclaw/security/
pscp -pw "%HOSTPWD%" src\telegram\bot_access.py src\telegram\bot_handlers.py stas@OpenClawPI2:/home/stas/.picoclaw/telegram/
pscp -pw "%HOSTPWD%" src\features\bot_mail_creds.py src\features\bot_calendar.py stas@OpenClawPI2:/home/stas/.picoclaw/features/
pscp -pw "%HOSTPWD%" src\bot_web.py stas@OpenClawPI2:/home/stas/.picoclaw/
pscp -pw "%HOSTPWD%" src\release_notes.json stas@OpenClawPI2:/home/stas/.picoclaw/

rem Step 13 — Restart & smoke
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI2 "echo %HOSTPWD% | sudo -S systemctl restart picoclaw-telegram picoclaw-web && sleep 5 && journalctl -u picoclaw-telegram -n 15 --no-pager"

rem Step 14 — Voice regression tests
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI2 "python3 /home/stas/.picoclaw/tests/test_voice_regression.py"

rem Step 15 — Web UI Playwright tests
py -m pytest src/tests/ui/test_ui.py -v --base-url https://openclawpi2:8080 --browser chromium
```

---

## Acceptance Criteria

- [ ] `journalctl -u picoclaw-telegram` shows `Version : 2026.3.34` and `Polling Telegram…`
- [ ] All T01–T13 voice regression tests PASS (T07/T08 still use same logic, just loaded from PROMPTS)
- [ ] Web UI Playwright: all TestAuth, TestDashboard, TestChat, TestCalendar, TestNotes tests PASS
- [ ] Changing a prompt template in `prompts.json` and restarting the service immediately reflects the change without code modification
