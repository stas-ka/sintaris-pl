# Taris — Conversation Architecture

**Version:** `2026.4.73`  
→ Architecture index: [architecture.md](../architecture.md)

---

## When to read this file
Changing how messages are sent to the LLM, modifying conversation history/memory, touching `bot_handlers.py` `_handle_chat_message`, `bot_access.py` `_build_system_message`/`_with_lang`/`fmt_prompt`, `prompts.json` templates, or `bot_state.py` history/summary functions.

---

## Multi-turn message structure (v2026.3.30+3)

```
[role:system]   ← _build_system_message(chat_id)    bot_access.py
                    = SECURITY_PREAMBLE
                    + bot config (name, version, variant)
                    + memory context (tiered summaries from prior sessions)
                    + language instruction
[role:user]     ← prior turn from chat_history DB
[role:assistant]← prior reply from chat_history DB
...
[role:user]     ← _user_turn_content(chat_id, text) bot_access.py
                    = RAG context (if docs match query)
                    + [USER]{text}[/USER]
```

**Rule:** `role:system` is prepended on **every** LLM call so the LLM always knows its identity.

---

## Key functions — where to change what

| Need to change | File | Function |
|---|---|---|
| Bot identity/preamble in LLM calls | `telegram/bot_access.py` | `_build_system_message()` |
| RAG injection into user turn | `telegram/bot_access.py` | `_user_turn_content()` |
| Single-turn voice/system-chat framing | `telegram/bot_access.py` | `_with_lang()` / `_with_lang_voice()` |
| Multi-turn LLM dispatch (all providers) | `core/bot_llm.py` | `ask_llm_with_history()` |
| Single-turn LLM dispatch | `core/bot_llm.py` | `ask_llm()` |
| Add/load history turns | `core/bot_state.py` | `add_to_history()` / `load_conversation_history()` |
| Tiered memory summarization | `core/bot_state.py` | `_summarize_session_async()` |
| Get summaries for injection | `core/bot_state.py` | `get_memory_context()` |
| Clear all memory tiers | `core/bot_state.py` | `clear_history()` |
| Text chat entry point | `telegram/bot_handlers.py` | `_handle_chat_message()` |
| Voice chat entry point | `features/bot_voice.py` | `_handle_voice_message()` |

---

## Tiered memory

```
chat_history (DB, live turns)
  → at CONV_SUMMARY_THRESHOLD (15 msgs): _summarize_session_async() [daemon thread]
        → insert into conversation_summaries tier='mid'
  → at CONV_MID_MAX (5 mid summaries): compact to tier='long'

Injection: get_memory_context() → appended to role:system at every call
Clear: Profile → 🗑 Clear memory → clear_history() deletes both tables
```

**Per-user memory toggle:** Profile → 🧠 Memory On/Off → writes `memory_enabled` to `user_prefs` table.  
When off: `get_memory_context()` returns empty string; no new summaries are generated.

**Admin memory settings:** Admin Panel → 🧠 Memory Settings → updates `system_settings` table:
- `CONVERSATION_HISTORY_MAX` — max turns in live window
- `CONV_SUMMARY_THRESHOLD` — turns before mid-tier summary
- `CONV_MID_MAX` — mid summaries before long-tier compaction

Handler: `telegram/bot_admin._handle_admin_memory_settings()`

---

## Text message routing (`telegram_menu_bot.py::text_handler`)

| Condition | Target |
|---|---|
| `_user_mode == "system"` | `_handle_system_message()` (admin-only NL→bash) |
| `_user_mode == "admin_rag_set_*"` | `_finish_admin_rag_set()` |
| `_user_mode == "doc_rename"` | `_handle_doc_rename_confirm()` |
| `chat_id in _pending_note` | note multi-step flow |
| `chat_id in _pending_contact` | contact book flows |
| `chat_id in _pending_cal` | calendar field-edit |
| default | `_handle_chat_message()` → `ask_llm_with_history()` |

---

## Voice routing (`bot_voice.py::_handle_voice_message`)

OGG → ffmpeg → PCM → STT → mode check:

| Mode | Target |
|---|---|
| `note_add_*` / `note_edit_content` | note creation/edit |
| `calendar` | `_finish_cal_add()` |
| `cal_console` | `_handle_cal_console()` |
| `cal_edit_*` | `_cal_handle_edit_input()` |
| `contact_*` | contact book |
| `system` | `_handle_system_message()` (admin only) |
| text starts with voice note keyword | quick note save/read |
| default | `ask_llm(_with_lang_voice())` → Piper TTS |

**Note:** Voice uses `ask_llm` (single-turn) — no history context. → ⏳ [TODO.md §2](../TODO.md#2-conversation--memory)

---

## Channel comparison

| Channel | LLM call | History | RAG |
|---|---|---|---|
| Telegram text | `ask_llm_with_history` | ✅ | ✅ |
| Web UI chat | `ask_llm_with_history` | ✅ | ✅ |
| Telegram voice | `ask_llm` (single-turn) | ❌ | ❌ |
| System chat | `ask_llm_with_history` | ✅ | ❌ |

---

## Context Data Sources — What the LLM knows

The following sources are combined into the LLM prompt at every text chat request:

| Source | How injected | Size limit | Who controls |
|---|---|---|---|
| Security preamble | `role:system` prefix | Fixed (~300 chars) | `SECURITY_PREAMBLE` constant |
| Bot identity (name, version, variant) | `role:system` | ~50 chars | `_build_system_message()` |
| Language instruction | `role:system` | ~30 chars | User language setting |
| Long-term memory (summary of summaries) | `role:system` | ~300–500 chars | Auto: `CONV_MID_MAX` threshold |
| Mid-term memory (session summaries) | `role:system` | ~200 chars each | Auto: `CONV_SUMMARY_THRESHOLD` |
| Live chat history (last N turns) | history messages | `CONV_MAX_HISTORY` turns | `load_conversation_history()` |
| RAG document chunks | `role:user` prefix | `RAG_TOP_K × RAG_CHUNK_SIZE` chars | `_user_turn_content()` |
| User text | `[USER]…[/USER]` | unlimited | user input |

**Sources NOT yet injected (planned):**

| Source | Status | TODO ref |
|---|---|---|
| User notes (personal KB) | ⏳ Planned | [TODO.md §10](../TODO.md) |
| Calendar events (today/upcoming) | ⏳ Planned | [TODO.md §10](../TODO.md) |
| Contact book entries | ⏳ Planned | [TODO.md §4](../TODO.md) |

→ Full knowledge source architecture: [knowledge-base.md](knowledge-base.md)

---

## Prompt Templates (v2026.4.73)

All LLM system prompt templates are defined in `src/prompts.json` and loaded by `src/telegram/bot_access.py`.

### Template structure

```json
{
  "role_system_prompts": {
    "user":   "...",
    "admin":  "...",
    "developer": "...",
    "guest":  "...",
    "voice":  "..."
  },
  "role_capabilities": {
    "user":      "calendar, contacts, notes, documents, email digest",
    "admin":     "...",
    "developer": "...",
    "guest":     "limited: ask questions, request access"
  },
  "style_guide": "..."
}
```

### Variable placeholders

| Placeholder | Filled by | Description |
|---|---|---|
| `{security_preamble}` | `SECURITY_PREAMBLE` constant | Anti-injection boilerplate |
| `{style_guide}` | `prompts["style_guide"]` | Tone, language, format rules |
| `{bot_capabilities}` | `prompts["role_capabilities"][role]` | Role-specific feature list |
| `{bot_config_block}` | `_bot_config_block()` | Bot name, version, variant (no capability list) |
| `{personal_ctx}` | `get_memory_context(chat_id)` | Tiered memory summaries |
| `{memory_note}` | note string if memory present | "You have a memory note:" prefix |
| `{lang_instruction}` | `_lang_instr(chat_id)` | Language preference instruction |
| `{calendar_summary}` | `_calendar_context(chat_id)` | Upcoming events (voice only) |

### How `_build_system_message()` works

```python
# telegram/bot_access.py
def _build_system_message(chat_id, user_text="", voice_mode=False):
    role_key = _get_prompt_role_key(chat_id)           # user | admin | developer | guest
    template_key = "voice" if voice_mode else role_key
    template = PROMPTS["role_system_prompts"][template_key]
    caps = PROMPTS["role_capabilities"].get(role_key, "")
    return fmt_prompt(template, bot_capabilities=caps, style_guide=..., ...)
```

- Voice mode → `voice` template (no markdown, max 2 sentences)
- Guest role → no calendar summary injected
- `_bot_config_block()` returns only `[BOT CONFIG]...[END BOT CONFIG]` (no capabilities — that's in the template)

### Key functions

| Function | File | What it does |
|---|---|---|
| `_build_system_message(chat_id, text, voice_mode)` | `telegram/bot_access.py` | Builds full system message for LLM call |
| `_bot_config_block()` | `telegram/bot_access.py` | Returns bot name/version/variant block |
| `fmt_prompt(template, **kwargs)` | `telegram/bot_access.py` | Variable substitution into template |
| `_get_prompt_role_key(chat_id)` | `telegram/bot_access.py` | Maps chat_id → role key (`user`/`admin`/etc.) |
| `_with_lang(chat_id, user_text)` | `telegram/bot_access.py` | Single-turn non-history LLM framing |

### Tests

T168–T172 in `src/tests/test_voice_regression.py` (`t_prompt_templates` function):

| Test | What it checks |
|---|---|
| T168 `prompt_voice_key_present` | `voice` key exists in `role_system_prompts` |
| T169 `prompt_templates_have_bot_capabilities` | All templates contain `{bot_capabilities}` |
| T170 `prompt_templates_have_style_guide` | All templates contain `{style_guide}` |
| T171 `bot_config_block_no_hardcoded_caps` | `_bot_config_block()` does not include capabilities |
| T172 `with_lang_role_aware` | `_with_lang()` injects capabilities block |
| T172b `build_system_message_voice_mode` | Voice mode selects `voice` template key |

---

## ⏳ Open items

| Item | TODO ref |
|---|---|
| Voice messages use conversation history | [TODO.md §2](../TODO.md#2-conversation--memory) |
| Per-user conversation isolation (multi-user admin guard) | [TODO.md §1](../TODO.md#1-access--security) |
