# Telegram Menu Bot — Code Map

**File:** `src/telegram_menu_bot.py`  
**Version:** 2026.3.19  
**Total lines:** ~2734

Use this map to jump directly to any function without searching.

---

## Constants & Globals (lines 1–322)

| Symbol | Line | Purpose |
|---|---|---|
| `BOT_VERSION` | 124 | `"YYYY.M.D"` — bump on every user-visible change |
| `BOT_TOKEN` | 107 | Telegram bot token from `bot.env` |
| `ALLOWED_USERS` | 108 | Comma-separated Telegram chat IDs |
| `ADMIN_USERS` | 109 | Subset of users with admin rights |
| `PICOCLAW_BIN` | 113 | `/usr/bin/picoclaw` |
| `PICOCLAW_CONFIG` | 114 | `~/.picoclaw/config.json` |
| `PIPER_BIN` | 115 | `/usr/local/bin/piper` |
| `PIPER_MODEL` | 237 | `~/.picoclaw/ru_RU-irina-medium.onnx` |
| `PIPER_MODEL_TMPFS` | 239 | `/dev/shm/piper/...` (RAM-disk copy) |
| `PIPER_MODEL_LOW` | 241 | `~/.picoclaw/ru_RU-irina-low.onnx` |
| `WHISPER_BIN` | 243 | `/usr/local/bin/whisper-cpp` |
| `WHISPER_MODEL` | 244 | `~/.picoclaw/ggml-tiny.bin` |
| `VOSK_MODEL_PATH` | 246 | `~/.picoclaw/vosk-model-small-ru/` |
| `_VOICE_OPTS_DEFAULTS` | 263 | All 10 voice-opt feature flags (all `False`) |
| `_user_mode` | 296 | `dict[int, str]` — `None` / `'chat'` / `'system'` per chat_id |
| `_pending_cmd` | 298 | `dict[int, str]` — bash cmd awaiting confirm |
| `_user_lang` | 300 | `dict[int, str]` — `'ru'` / `'en'` per chat_id |
| `_vosk_model_cache` | 301 | Vosk model singleton (lazy-loaded) |
| `_persistent_piper_proc` | 302 | §5.3 keepalive Piper subprocess or `None` |
| `_pending_llm_key` | 303 | LLM API key input state per chat_id |
| `_user_audio` | 304 | Per-user audio on/off toggle |
| `_pending_note` | 305 | Notes multi-step input state per chat_id |
| `_voice_opts` | ~340 | Live dict loaded from `voice_opts.json` |

---

## Functions by Domain

### Env / Config Loading (lines 67–230)

| Function | Line | Purpose |
|---|---|---|
| `_load_env_file(path)` | 67 | Parse `KEY=VALUE` file → `os.environ` |
| `_parse_allowed_users()` | 85 | Read `ALLOWED_USERS` / `ALLOWED_USER` / `TELEGRAM_CHAT_ID` |
| `_parse_admin_users()` | 98 | Read `ADMIN_USERS` / `ADMIN_USER_ID` |
| `_load_dynamic_users()` | 138 | Load `dynamic_users.json` (approved via reg flow) |
| `_save_dynamic_users()` | 145 | Persist `dynamic_users.json` |
| `_load_registrations()` | 161 | Load `registrations.json` (pending/blocked/approved) |
| `_save_registrations(regs)` | 170 | Persist `registrations.json` |
| `_find_registration(chat_id)` | 180 | Get reg dict for a chat_id or `None` |
| `_upsert_registration(...)` | 187 | Create or update registration record |
| `_set_reg_status(chat_id, status)` | 209 | Set `pending` / `approved` / `blocked` |
| `_get_pending_registrations()` | 218 | List all pending regs |
| `_is_blocked_reg(chat_id)` | 222 | Check blocked status |
| `_is_pending_reg(chat_id)` | 227 | Check pending status |

### Voice Opts (lines 255–357)

| Function | Line | Purpose |
|---|---|---|
| `_load_voice_opts()` | 323 | Load `voice_opts.json` → merge with defaults |
| `_save_voice_opts()` | 337 | Persist `_voice_opts` to disk |

### Access Control (lines 358–388)

| Function | Line | Purpose |
|---|---|---|
| `_is_allowed(chat_id)` | 358 | True if static + dynamic + admin |
| `_is_admin(chat_id)` | 362 | True if in `ADMIN_USERS` |
| `_is_guest(chat_id)` | 365 | True if not allowed (incl. pending/blocked) |
| `_deny(chat_id)` | 369 | Send "access denied" message |

### i18n / Strings (lines 389–432)

| Function | Line | Purpose |
|---|---|---|
| `_load_strings(path)` | 389 | Load `strings.json` |
| `_set_lang(chat_id, from_user)` | 409 | Auto-detect and cache user language |
| `_lang(chat_id)` | 418 | Get `'ru'` / `'en'` for chat_id |
| `_t(chat_id, key, **kwargs)` | 423 | Get translated string by key |

### Keyboards / UI Helpers (lines 434–535)

| Function | Line | Purpose |
|---|---|---|
| `_menu_keyboard(chat_id)` | 434 | Main menu inline keyboard |
| `_back_keyboard()` | 450 | Single `← Back` button |
| `_voice_back_keyboard(chat_id)` | 456 | Voice menu back button |
| `_confirm_keyboard(cmd_hash)` | 467 | Confirm / Cancel for system commands |
| `_send_menu(chat_id, greeting)` | 476 | Send main menu message |
| `_truncate(text, limit)` | 484 | Truncate to 3800 chars (Telegram limit) |
| `_safe_edit(chat_id, msg_id, text, ...)` | 490 | Edit message, ignore `message_not_modified` errors |
| `_run_subprocess(cmd, timeout, ...)` | 499 | Run shell command, return `(stdout, rc)` |

### LLM / picoclaw Integration (lines 520–611)

| Function | Line | Purpose |
|---|---|---|
| `_ask_picoclaw(prompt, timeout)` | 520 | Run `picoclaw agent -m "..."`, return output |
| `_clean_picoclaw_output(text)` | 547 | Strip ANSI / spinner artefacts from CLI output |

### Language Detection (lines 612–707)

| Function | Line | Purpose |
|---|---|---|
| `_detect_text_lang(text)` | 612 | Heuristic: detect `'ru'` / `'en'` / `None` from chars |
| `_resolve_lang(chat_id, user_text)` | 636 | Merge user pref + text detection |
| `_with_lang(chat_id, user_text)` | 660 | Build language-hint prefix for LLM prompt |
| `_with_lang_voice(chat_id, stt_text)` | 667 | Same, but for voice → LLM path |

### Text Utilities (lines 708–737)

| Function | Line | Purpose |
|---|---|---|
| `_escape_tts(text)` | 708 | Strip Markdown/ANSI for TTS input |
| `_escape_md(text)` | 727 | Escape for Telegram MarkdownV2 |

### Admin Menu Handlers (lines 738–929)

| Function | Line | Purpose |
|---|---|---|
| `_admin_keyboard()` | 738 | Admin inline keyboard |
| `_handle_admin_menu(chat_id)` | 756 | Show admin panel |
| `_handle_admin_list_users(chat_id)` | 765 | List allowed users |
| `_start_admin_add_user(chat_id)` | 779 | Prompt for user ID to add |
| `_finish_admin_add_user(admin_id, text)` | 788 | Validate + add user |
| `_start_admin_remove_user(chat_id)` | 813 | Prompt for user ID to remove |
| `_finish_admin_remove_user(admin_id, text)` | 827 | Validate + remove user |
| `_handle_admin_pending_users(chat_id)` | 849 | Show pending registration list with approve/block buttons |
| `_do_approve_registration(admin_id, target_id)` | 884 | Approve + notify user |
| `_do_block_registration(admin_id, target_id)` | 909 | Block + notify user |

### Notes System (lines 930–1090)

| Function | Line | Purpose |
|---|---|---|
| `_slug(title)` | 930 | `title → safe-filename-slug` |
| `_notes_user_dir(chat_id)` | 939 | `~/.picoclaw/notes/<chat_id>/` |
| `_list_notes_for(chat_id)` | 946 | Return `[{slug, title, mtime}]` sorted newest-first |
| `_load_note_text(chat_id, slug)` | 959 | Read note file content |
| `_save_note_file(chat_id, slug, content)` | 967 | Write note file |
| `_delete_note_file(chat_id, slug)` | 974 | Delete note file, return `True` if existed |
| `_notes_menu_keyboard(chat_id)` | 984 | Notes submenu keyboard |
| `_notes_list_keyboard(chat_id, notes)` | 995 | Paginated note list keyboard |
| `_handle_notes_menu(chat_id)` | 1011 | Show notes menu |
| `_handle_note_list(chat_id)` | 1020 | Show list of notes |
| `_start_note_create(chat_id)` | 1033 | Begin note creation (title step) |
| `_handle_note_open(chat_id, slug)` | 1040 | Show note read view |
| `_start_note_edit(chat_id, slug)` | 1060 | Begin note edit (content step) |
| `_handle_note_delete(chat_id, slug)` | 1076 | Delete note + confirm |

### Voice Opts Menu (lines 1091–1159)

| Function | Line | Purpose |
|---|---|---|
| `_handle_voice_opts_menu(chat_id)` | 1091 | Show all 10 opt toggles with current flags |
| `_handle_voice_opt_toggle(chat_id, key)` | 1132 | Flip opt, save, refresh menu; side-effects for `persistent_piper` / `tmpfs_model` |

### Release Notes / Version (lines 1160–1297)

| Function | Line | Purpose |
|---|---|---|
| `_load_release_notes()` | 1160 | Load `release_notes.json` |
| `_format_release_entry(entry, header)` | 1169 | Format one entry for Telegram message |
| `_get_changelog_text(max_entries)` | 1179 | Full or truncated changelog string |
| `_notify_admins_new_version()` | 1251 | Send release notes to admins once per `BOT_VERSION` |
| `_handle_admin_changelog(chat_id)` | 1294 | Show full changelog in admin panel |

### LLM Provider Management (lines 1314–1528)

| Function | Line | Purpose |
|---|---|---|
| `_get_active_model()` | 1314 | Read active model name from `config.json` |
| `_set_active_model(model_name)` | 1322 | Write active model name to `config.json` |
| `_get_picoclaw_models()` | 1331 | List all models from `config.json` |
| `_handle_admin_llm_menu(chat_id)` | 1341 | Show LLM selector + OpenAI setup button |
| `_handle_set_llm(chat_id, model_name)` | 1386 | Switch active model |
| `_get_shared_openai_key()` | 1415 | Read OpenAI key from `config.json` |
| `_save_openai_apikey(api_key)` | 1423 | Write OpenAI key + inject into `bot.env` |
| `_handle_openai_llm_menu(chat_id)` | 1448 | OpenAI key management submenu |
| `_handle_llm_setkey_prompt(chat_id)` | 1485 | Prompt user to paste API key |
| `_handle_save_llm_key(chat_id, raw_key)` | 1502 | Validate + store API key |

### Gmail Digest (lines 1529–1592)

| Function | Line | Purpose |
|---|---|---|
| `_handle_digest(chat_id)` | 1529 | Show last digest or trigger refresh |
| `_refresh_digest(chat_id)` | 1554 | Run `gmail_digest.py`, show spinner |

### Message Handlers (lines 1593–1715)

| Function | Line | Purpose |
|---|---|---|
| `_handle_system_message(chat_id, user_text)` | 1593 | Validate + confirm-gate shell commands |
| `_execute_pending_cmd(chat_id)` | 1636 | Run confirmed command via `_run_subprocess` |
| `_handle_chat_message(chat_id, user_text)` | 1672 | Route text to `_ask_picoclaw`, stream reply |

### Voice Pipeline (lines 1716–2277)

| Function | Line | Purpose |
|---|---|---|
| `_get_vosk_model()` | 1716 | Lazy-load Vosk model singleton |
| `_piper_model_path()` | 1726 | Priority: tmpfs → low → medium |
| `_setup_tmpfs_model(enable)` | 1738 | Copy/remove ONNX to `/dev/shm/piper/` |
| `_warm_piper_cache()` | 1766 | Pre-run Piper with empty input to warm ONNX |
| `_start_persistent_piper()` | 1787 | Launch keepalive Piper subprocess (§5.3) |
| `_stop_persistent_piper()` | 1807 | Terminate keepalive subprocess (§5.3) |
| `_vad_filter_pcm(raw_pcm, sample_rate)` | 1821 | WebRTC VAD: remove non-speech frames (§5.3) |
| `_stt_whisper(raw_pcm, sample_rate)` | 1851 | STT via whisper.cpp binary (§5.3) |
| `_tts_to_ogg(text)` | 1898 | Piper → raw PCM → ffmpeg → OGG bytes |
| `_start_voice_session(chat_id)` | 1968 | Initialize per-user voice session state |
| `_handle_voice_message(chat_id, voice_obj)` | 1979 | Full voice pipeline: OGG→PCM→VAD→STT→LLM→TTS→send |

### Telegram Handlers / Main (lines 2278–2734)

| Function | Line | Purpose |
|---|---|---|
| `cmd_start(message)` | 2278 | `/start` — registration flow or send menu |
| `_notify_admins_new_registration(...)` | 2304 | Alert admins with approve/block buttons |
| `handle_callback(call)` | ~2320 | Central callback dispatcher (all `data=` keys) |
| `handle_message(message)` | ~2600 | Route text/voice messages |
| `main()` | ~2690 | Init → startup side-effects → `bot.polling()` |

---

## Callback Data Key Reference

All inline button `data=` strings routed through `handle_callback()`:

| Prefix / Key | Handler called |
|---|---|
| `menu` | `_send_menu` |
| `admin` | `_handle_admin_menu` |
| `admin_list_users` | `_handle_admin_list_users` |
| `admin_add_user` | `_start_admin_add_user` |
| `admin_remove_user` | `_start_admin_remove_user` |
| `admin_pending` | `_handle_admin_pending_users` |
| `admin_approve_<id>` | `_do_approve_registration` |
| `admin_block_<id>` | `_do_block_registration` |
| `admin_llm` | `_handle_admin_llm_menu` |
| `admin_openai` | `_handle_openai_llm_menu` |
| `admin_llm_setkey` | `_handle_llm_setkey_prompt` |
| `admin_set_llm_<model>` | `_handle_set_llm` |
| `admin_changelog` | `_handle_admin_changelog` |
| `admin_voice_opts` | `_handle_voice_opts_menu` |
| `voice_opt_toggle_<key>` | `_handle_voice_opt_toggle` |
| `digest` | `_handle_digest` |
| `digest_refresh` | `_refresh_digest` |
| `notes` | `_handle_notes_menu` |
| `note_list` | `_handle_note_list` |
| `note_create` | `_start_note_create` |
| `note_open_<slug>` | `_handle_note_open` |
| `note_edit_<slug>` | `_start_note_edit` |
| `note_del_<slug>` | `_handle_note_delete` |
| `chat` | set `_user_mode[id]='chat'` |
| `system` | set `_user_mode[id]='system'` |
| `confirm_<hash>` | `_execute_pending_cmd` |
| `cancel_confirm` | clear pending cmd |
| `voice_toggle` | toggle `_user_audio[id]` |

---

## Key Files on Pi (runtime)

| File | Purpose |
|---|---|
| `~/.picoclaw/bot.env` | Secrets: `BOT_TOKEN`, `ALLOWED_USERS`, `ADMIN_USERS`, `OPENROUTER_API_KEY` |
| `~/.picoclaw/voice_opts.json` | Persisted voice opt flags |
| `~/.picoclaw/pending_tts.json` | TTS orphan-cleanup tracking |
| `~/.picoclaw/dynamic_users.json` | Dynamically approved users |
| `~/.picoclaw/registrations.json` | User registration records |
| `~/.picoclaw/last_notified_version.txt` | Last `BOT_VERSION` admin was notified about |
| `~/.picoclaw/notes/<chat_id>/<slug>.md` | Per-user note files |
| `~/.picoclaw/config.json` | picoclaw LLM config (model_list, agents) |
| `~/.picoclaw/telegram_bot.log` | Bot log file |
