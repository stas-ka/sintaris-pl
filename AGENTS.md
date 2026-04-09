# Agent Memory — taris


This file stores persistent state for AI coding agents. See `.github/copilot-instructions.md` for full workspace instructions.

## User Working Preferences
- Keep persistent operational knowledge in this file so future sessions can continue quickly.
- Use this file as the first reference for recurring document/accounting tasks.
- **Testing ("test software" / "run tests" / "verify changes"):** always read `doc/test-suite.md` first — it has the complete decision table, all run commands, and the Copilot chat-mode protocol. Never scan test files manually every session.
- **Context optimization:** Start every session with `#file:doc/quick-ref.md`. Avoid `@workspace`. Use `/skill-name` for deploy/test workflows. Keep sessions ≤ 10 turns to avoid compaction.

## Remote Host — Raspberry Pi targets (taris branch)

> ⚠️ **PI1 Branch Rule**: PI1 (`OpenClawPI`) only receives deployments from the **`master` branch**. PI2 (`OpenClawPI2`) may receive any branch for development/testing.

| Key | Value |
|---|---|
| `DEV_TARGETHOST` | `OpenClawPI2` |
| `DEV_HOSTUSER` | `stas` |
| `DEV_TAILSCALE_IP` | `100.81.143.126` |
| SSH | `plink -pw "%DEV_HOSTPWD%" -batch stas@OpenClawPI2 "<cmd>"` (LAN) |
| SSH remote | `plink -pw "%DEV_HOSTPWD%" -batch stas@XXX.XXX.XXX.XXX "<cmd>"` (Tailscale) |
| `PROD_TARGETHOST` | `OpenClawPI` |
| `PROD_HOSTUSER` | `stas` |
| `PROD_TAILSCALE_IP` | `100.81.143.126` |
| SSH | `plink -pw "PROD_%HOSTPWD%" -batch stas@OpenClawPI "<cmd>"` (LAN) |
| SSH remote | `plink -pw "%PROD_HOSTPWD%" -batch stas@100.81.143.126 "<cmd>"` (Tailscale) |

## OpenClaw Targets (master branch)

> ⚠️ **TariStation1 Branch Rule**: TariStation1 (`SintAItion`) only receives deployments from the **`master` branch**. TariStation2 may receive any branch for development/testing.
> ⚠️ **TariStation1 Confirmation Rule**: Deploy to TariStation1 ONLY after explicit user/owner confirmation. Always deploy to TariStation2 first and verify all tests pass.

### TariStation2 — Engineering target (IniCoS-1, remote Lubuntu Linux)

| Key | Value |
|---|---|
| `ENG_TARGETHOST` | `IniCoS-1` — remote Lubuntu 24.04, i7-2640M, 7.6GB RAM |
| `ENG_TARGETHOST_IP` | `192.168.178.27` |
| `ENG_HOSTUSER` | `stas` |
| `ENG_HOSTPWD` | `buerger` (in `.env`) |
| `ENG_HOSTKEY` | `SHA256:2Psz9uCmafYyM25q7XAjmdwIV1YhBzX6KfSzn/zqmhE` |
| SSH | `plink -pw "buerger" -hostkey "%ENG_HOSTKEY%" -batch stas@192.168.178.27 "<cmd>"` |
| SCP | `pscp -pw "buerger" -hostkey "%ENG_HOSTKEY%" src\file.py stas@192.168.178.27:/home/stas/.taris/` |
| Deploy path | `/home/stas/.taris/` |
| Project | `~/projects/sintaris-pl` (on target) |
| DB | SQLite (`~/.taris/taris.db`) |
| Ollama | ❌ Not installed — install before LLM/Gemma4 eval |

### TariStation1 — Production target (SintAItion, remote Ubuntu Linux)

| Key | Value |
|---|---|
| `PROD_OPENCLAW_HOST` | `SintAItion.local` (`192.168.178.175`) |
| `PROD_OPENCLAW_USER` | `stas` |
| `OPENCLAW1PWD` | `buerger` (in `.env`) |
| `OPENCLAW1_HOSTKEY` | `SHA256:QetDJFNpeIuKlHqZI7z/N4YjZy4uTcgCUq0zgExBn74` |
| SSH | `plink -pw "buerger" -hostkey "%OPENCLAW1_HOSTKEY%" -batch stas@SintAItion.local "<cmd>"` |
| SCP | `pscp -pw "buerger" -hostkey "%OPENCLAW1_HOSTKEY%" src\file.py stas@SintAItion.local:/home/stas/.taris/` |
| Deploy path | `/home/stas/.taris/` |
| Project | `~/projects/sintaris-pl` (on target) |
| DB | PostgreSQL (migrated 2026-04) |
| Ollama | ✅ Installed, AMD ROCm 890M GPU, qwen3.5:latest |
| Skill | `/taris-deploy-openclaw-target` |

## Current Bot Version

`BOT_VERSION = "2026.3.48"` — deployed 2026-03-31

## Current LLM Config

### SintAItion (TariStation1)
- `LLM_PROVIDER=ollama` ← **primary** (switched 2026-04-09)
- `OLLAMA_MODEL=gemma4:e2b` — 92% quality RU/DE/EN @ 45 t/s
- `LLM_FALLBACK_PROVIDER=openai` (gpt-4o-mini fallback if Ollama fails)
- Also available: `gemma4:e4b` (25 t/s, same quality; swap OLLAMA_MODEL to switch)

### TariStation2
- `LLM_PROVIDER=ollama` ← **primary** (switched 2026-04-09)
- `OLLAMA_MODEL=qwen3.5:0.8b` — best fit for 7.6 GB RAM
- `LLM_FALLBACK_PROVIDER=ollama` (gemma4 doesn't fit, kept qwen3.5)

> Note: de_reasoning benchmark fails on ALL models (known timezone arithmetic benchmark limitation)

## Current STT Config (SintAItion)

- `FASTER_WHISPER_MODEL=small` int8 — best all-round (RU=22%/DE=22%/EN=14% WER, RTF=0.34)
- large-v3-turbo is better for DE(6%) but >real-time (RTF=1.3)

## Current Feature State (v2026.3.48)

### Calendar
- **Multi-Event Add:** LLM returns `{"events": [{title, dt}, ...]}`. 1 event → single confirm. N events → sequential "1 of N" with Save / Skip / Save All.
- **NL Query:** `_handle_calendar_query(chat_id, text)` — LLM extracts `{from, to, label}` date range.
- **Delete Confirmation:** `cal_del:<id>` → confirm card → `cal_del_confirm:<id>` → delete.
- **Console Mode:** button **💬 Консоль** → `_user_mode = "cal_console"` → LLM classifies intent: `add | query | delete | edit`.
- **Rule:** all calendar mutations require explicit confirmation (add → confirm → save; delete → confirm → delete).

## Vibe Coding Protocol — MANDATORY

After every completed request, append a row to `doc/vibe-coding-protocol.md`.

| Field | How to measure |
|---|---|
| `Time` | UTC timestamp from `<current_datetime>` tag |
| `Time start` | UTC timestamp from `<start_datetime>` tag |
| `Time end` |UTC timestamp from `<end_datetime>` tag |
| `Duration` | duration from `<duration>` tag |
| `Request` | One-line description |
| `Steps/Todos` | One-line description |
| `Complexity` | 1 (trivial) – 5 (architecture change) |
| `Requests used` | Number of user→assistant turns |
| `Model` | Model ID from `<model_information>` tag |
| `Files changed` | Comma-separated list |
| `Status` | `done` / `partial` / `wip` |

Row format:
```
| HH:MM UTC | | HH:MM UTC || HH:MM UTC | MM |description | 1–5 | N turns | model-id | files | done |
```
