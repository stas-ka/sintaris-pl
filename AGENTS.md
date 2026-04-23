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
| `DEV_TAILSCALE_IP` | `$DEV_TAILSCALE_IP` (see `.env`) |
| SSH | `plink -pw "%DEV_HOSTPWD%" -batch stas@OpenClawPI2 "<cmd>"` (LAN) |
| SSH remote | `plink -pw "%DEV_HOSTPWD%" -batch stas@%DEV_TAILSCALE_IP% "<cmd>"` (Tailscale) |
| `PROD_TARGETHOST` | `OpenClawPI` |
| `PROD_HOSTUSER` | `stas` |
| `PROD_TAILSCALE_IP` | `$PROD_TAILSCALE_IP` (see `.env`) |
| SSH | `plink -pw "PROD_%HOSTPWD%" -batch stas@OpenClawPI "<cmd>"` (LAN) |
| SSH remote | `plink -pw "%PROD_HOSTPWD%" -batch stas@%PROD_TAILSCALE_IP% "<cmd>"` (Tailscale) |

## OpenClaw Targets (master branch)

> ⚠️ **Branch Rules**: TariStation1 and VPS-Supertaris only receive deployments from the **`master` branch**. TariStation2 may receive any branch for development/testing.
> ⚠️ **Confirmation Rules**: Deploy to TariStation1 and VPS-Supertaris ONLY after explicit user/owner confirmation. Always deploy to TariStation2 first and verify all tests pass.
> ⚠️ **VPS-only coding rule**: When programming from VPS (code-server on agents.sintaris.net / VPS-Supertaris), TariStation2 is not reachable from the VPS network. In this case, **skip the TS2 step and deploy directly to VPS only**. Do not attempt to deploy to TariStation2 or TariStation1 from the VPS.

**OpenClaw has 3 deployment targets:**

| Target | Alias | Environment | Risk |
|---|---|---|---|
| TariStation2 | IniCoS-1 | Engineering (local LAN) | Low |
| TariStation1 | SintAItion | Production (home LAN / Tailscale) | Medium — shared machine |
| VPS-Supertaris | agents.sintaris.net | Internet-facing production | 🔴 HIGH — shared public VPS |

### TariStation2 — Engineering target (IniCoS-1, remote Lubuntu Linux)

| Key | Value |
|---|---|
| `ENG_TARGETHOST` | `IniCoS-1` — remote Lubuntu 24.04, i7-2640M, 7.6GB RAM |
| `ENG_TARGETHOST_IP` | `$ENG_TARGETHOST_IP` (see `.env`) |
| `ENG_HOSTUSER` | `stas` |
| `ENG_HOSTPWD` | `$ENG_HOSTPWD` (in `.env` — never commit the value) |
| `ENG_HOSTKEY` | `$ENG_HOSTKEY` (in `.env` — never commit the value) |
| SSH | `plink -pw "$ENG_HOSTPWD" -hostkey "$ENG_HOSTKEY" -batch stas@$ENG_TARGETHOST_IP "<cmd>"` |
| SCP | `pscp -pw "$ENG_HOSTPWD" -hostkey "$ENG_HOSTKEY" src\file.py stas@$ENG_TARGETHOST_IP:/home/stas/.taris/` |
| Deploy path | `/home/stas/.taris/` |
| Project | `~/projects/sintaris-pl` (on target) |
| DB | SQLite (`~/.taris/taris.db`) |
| Ollama | ❌ Not installed — install before LLM/Gemma4 eval |

### TariStation1 — Production target (SintAItion, remote Ubuntu Linux)

> 🚨 **SHARED PRODUCTION VPS** — hosts PostgreSQL, N8N, Nginx, other bots and services in addition to taris.  
> **ALL changes** (code deploy, service restarts, service file updates, package installs, database migrations, system config changes) require **explicit confirmation from the user (stas) before execution.**  
> Present the VPS pre-checklist from the SKILL.md before any TS1 operation. Never bundle multiple operation types into one confirmation — ask separately for each.

| Key | Value |
|---|---|
| `PROD_OPENCLAW_HOST` | `SintAItion.local` |
| `PROD_OPENCLAW_USER` | `stas` |
| `OPENCLAW1PWD` | `$OPENCLAW1PWD` (in `.env` — never commit the value) |
| `OPENCLAW1_HOSTKEY` | `$OPENCLAW1_HOSTKEY` (in `.env` — never commit the value) |
| SSH | `plink -pw "$OPENCLAW1PWD" -hostkey "$OPENCLAW1_HOSTKEY" -batch stas@SintAItion.local "<cmd>"` |
| SCP | `pscp -pw "$OPENCLAW1PWD" -hostkey "$OPENCLAW1_HOSTKEY" src\file.py stas@SintAItion.local:/home/stas/.taris/` |
| Deploy path | `/home/stas/.taris/` |
| Project | `~/projects/sintaris-pl` (on target) |
| DB | PostgreSQL (migrated 2026-04) — shared VPS database |
| Ollama | ✅ Installed, AMD ROCm 890M GPU, qwen3.5:latest |
| Skill | `/taris-deploy-openclaw-target` |

**VPS co-located services (do not disrupt):**
- PostgreSQL — shared database server
- N8N workflow engine
- Nginx reverse proxy
- Other bot services

### VPS-Supertaris — Internet-facing production target (agents.sintaris.net)

> 🔴 **HIGHEST RISK TARGET — SHARED PUBLIC INTERNET VPS.**  
> This VPS is **directly internet-facing** and hosts multiple critical services:  
> PostgreSQL (shared DB), N8N (workflow engine), Nginx (reverse proxy for all bots), other bots and apps.  
> taris runs here as `systemctl --user taris-telegram taris-web` behind the Nginx `/supertaris/` sub-path.  
> **ALL operations require explicit confirmation from the user (stas) before execution — NO EXCEPTIONS.**  
> **Never run `apt upgrade`, `apt install`, database DDL, or Nginx changes without explicit confirmation.**

| Key | Value |
|---|---|
| Hostname | `agents.sintaris.net` |
| `VPS_HOST` | `$VPS_HOST` (in `.env` — never commit) |
| `VPS_USER` | `$VPS_USER` (in `.env` — never commit) |
| `VPS_PWD` | `$VPS_PWD` (in `.env` — never commit) |
| `VPS_HOSTKEY` | `$VPS_HOSTKEY` (in `.env` — never commit) |
| SSH | `ssh -i ~/.ssh/vps_key $VPS_USER@$VPS_HOST "<cmd>"` or `sshpass -p "$VPS_PWD" ssh $VPS_USER@$VPS_HOST` |
| Deploy path | `/home/$VPS_USER/.taris/` |
| Web UI path | `https://agents.sintaris.net/supertaris/` |
| ROOT_PATH | `/supertaris` (set in `~/.taris/bot.env`) |
| DB | PostgreSQL — shared VPS database (same server as N8N and other bots) |
| Ollama | depends on VPS resources |
| Nginx config | `/etc/nginx/sites-available/agents.sintaris.net` |
| Skill | `/taris-deploy-openclaw-target` (target=`vps`) |

**VPS co-located services (do not disrupt):**
- PostgreSQL — shared database for multiple applications
- N8N workflow engine (production automation)
- Nginx reverse proxy (serves all bots + apps via sub-paths)
- Other bots and web services

**Forbidden autonomous actions on VPS-Supertaris:**
- ❌ `apt upgrade`, `apt install`, `pip install --upgrade` without confirmation
- ❌ Any Nginx config change without confirmation (affects ALL apps on VPS)
- ❌ PostgreSQL DDL (CREATE/DROP/ALTER TABLE) without confirmation + backup
- ❌ Restart shared services (PostgreSQL, Nginx, N8N) without confirmation
- ❌ Firewall changes (`ufw`, `iptables`) without confirmation
- ❌ Restart taris services without confirmation (brief downtime visible publicly)

`BOT_VERSION = "2026.3.48"` — deployed 2026-03-31

## Current LLM Config

### SintAItion (TariStation1)
- `LLM_PROVIDER=ollama` ← **primary**
- `OLLAMA_MODEL=qwen3.5:latest` (9B) — **100% quality RU/DE/EN/SL @ ~13 t/s** (restored 2026-04-09; gemma4:e2b was too small → circular answers)
- `LOCAL_MAX_TOKENS=512` (increased from 256 which caused truncation/circular text)
- `LLM_FALLBACK_PROVIDER=openai` (gpt-4o-mini fallback if Ollama fails)
- Admin model picker available: Admin → LLM Settings → 🦙 Ollama model picker

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
