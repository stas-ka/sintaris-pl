# Taris — Multilanguage Support

**Version:** `2026.3.28`  
→ Architecture index: [architecture.md](../architecture.md)

---

## 14. Multilanguage Support

> **Status (2026-03-11):** Phase 1 and Phase 2 complete — all modules migrated to `_t()`. Deployed 2026-03-11.

### 14.1 Concept

The bot automatically detects each user's language from Telegram's `language_code` field and responds consistently in that language across all surfaces: UI buttons, bot messages, LLM responses, and TTS voice output.

```
User sends message / taps button
        │
        ▼
_set_lang(chat_id, from_user)
        │   reads Telegram language_code
        │   "ru*" → ru  |  "de*" → de  |  else → en
        ▼
_user_lang[chat_id] = "ru" | "de" | "en"   ← stored per session
        │
        ├── UI strings   → _t(chat_id, key)      ← looks up strings.json[lang][key]
        │
        ├── LLM replies  → _LANG_INSTRUCTION[lang]  ← prepended to every LLM prompt
        │                    "Antworte ausschließlich auf Deutsch…"
        │
        └── Voice (TTS)  → _piper_model_path(lang) ← selects language-specific ONNX
             Voice (STT)  → _get_vosk_model(lang)   ← selects language-specific Vosk
```

### 14.2 Supported Languages

| Code | Language | UI strings | LLM prompt | STT model | TTS model |
|------|----------|------------|------------|-----------|-----------|
| `ru` | Russian | ✅ 115 keys | ✅ | `vosk-model-small-ru` | `ru_RU-irina-medium.onnx` |
| `de` | German | ✅ 115 keys | ✅ | `vosk-model-small-de` *(optional)* | `de_DE-thorsten-medium.onnx` *(optional)* |
| `en` | English | ✅ 115 keys | ✅ | fallback: `vosk-model-small-ru` | fallback: `ru_RU-irina-medium.onnx` |

If a German/English voice model is absent, the pipeline falls back to Russian models with a warning log.

### 14.3 i18n String System

**`strings.json`** — flat JSON with one top-level object per language code:

```json
{
  "ru": { "welcome": "…", "btn_chat": "💬 Чат", … },
  "de": { "welcome": "…", "btn_chat": "💬 Chat", … },
  "en": { "welcome": "…", "btn_chat": "💬 Chat", … }
}
```

**`_t(chat_id, key, **kwargs)`** — the single string lookup function:
```python
lang = _user_lang.get(chat_id, "ru")
text = _STRINGS.get(lang, _STRINGS.get("en", {})).get(key, key)
return text.format(**kwargs) if kwargs else text
```
- Falls back: user lang → "en" → key name (never crashes)
- Supports `{placeholder}` substitution: `_t(cid, "note_saved", title="My note")`

**All 188 UI keys** are present in all three languages. All dynamic/inline strings in `bot_calendar.py`, `bot_handlers.py`, `bot_mail_creds.py`, and `bot_access.py` are fully migrated to `_t()` (Phase 2 complete).

### 14.4 LLM Language Injection

Every LLM call is prefixed with a language instruction from `_LANG_INSTRUCTION`:

| Lang | Instruction |
|------|-------------|
| `ru` | "Отвечай строго на русском языке. Не используй эмоджи…" |
| `de` | "Antworte ausschließlich auf Deutsch. Verwende keine Emojis…" |
| `en` | "Reply in English only. Do not use emoji…" |

For voice input with uncertain words `[?word]`, an additional STT-correction hint is injected in the user's language.

### 14.5 Per-Language Voice Pipeline

```
STT: _get_vosk_model(lang)
        lang == "de"  →  VOSK_MODEL_DE_PATH  (~/.taris/vosk-model-small-de)
        else          →  VOSK_MODEL_PATH      (~/.taris/vosk-model-small-ru)
        fallback: log warning + use Russian model

TTS: _piper_model_path(lang)
        lang == "de"
          tmpfs_model ON  →  PIPER_MODEL_DE_TMPFS  (/dev/shm/piper/de_DE-thorsten-medium.onnx)
          else            →  PIPER_MODEL_DE         (~/.taris/de_DE-thorsten-medium.onnx)
          not found       →  log warning + fall back to Russian model
        else
          → standard RU model priority chain (tmpfs → low → medium)
```

Both Vosk and Piper models are loaded lazily on first use; not at startup.

### 14.6 Implementation Status

| Component | Status | Details |
|-----------|--------|---------|
| Language detection (`_set_lang`) | ✅ Done | Detects ru/de/en from Telegram `language_code` |
| `strings.json` DE translations | ✅ Done | All 115 keys translated |
| LLM prompt injection | ✅ Done | German instruction in `_LANG_INSTRUCTION` |
| STT model routing | ✅ Done | `_get_vosk_model(lang)` in `bot_voice.py` |
| TTS model routing | ✅ Done | `_piper_model_path(lang)` in `bot_voice.py` |
| TTS `lang=` pass-through | ✅ Done | All `_tts_to_ogg()` calls pass `lang=` |
| Inline strings in `bot_calendar.py` | ✅ Done | All ternaries replaced with `_t()` |
| Inline strings in `bot_handlers.py` | ✅ Done | All labels migrated |
| Inline strings in `bot_mail_creds.py` | ✅ Done | All strings + DE provider hints |
| Inline strings in `bot_access.py` | ✅ Done | deny, back, mute labels |
| `setup_voice.sh` German models | ✅ Done | vosk-small-de + de_DE-thorsten-medium downloads |
| **Deployed to Pi** | ✅ Done | Deployed 2026-03-11, v2026.3.26 |

### 14.7 Adding a New Language

To add a 4th language (e.g. French `fr`):

1. Add `"fr": { … }` section to `strings.json` — 115 keys
2. Add `"fr"` to `_SUPPORTED_LANGS` in `bot_access.py`
3. Add `elif lc.startswith("fr"): _user_lang[chat_id] = "fr"` to `_set_lang()`
4. Add French instruction to `_LANG_INSTRUCTION`
5. Add French Vosk model path to `bot_config.py` + `_get_vosk_model()` branch
6. Add French Piper voice model path to `bot_config.py` + `_piper_model_path()` branch
7. Add French model downloads to `setup_voice.sh`
