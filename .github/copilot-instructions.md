# Copilot Instructions — taris workspace

## Available Skills (Prompt Files)

These reusable task prompts live in `.github/prompts/`. Invoke them with `/skill-name` in VS Code Copilot Chat (requires VS Code 1.99+ with `chat.promptFiles: true` — already set in `.vscode/settings.json`).

| `/skill-name` | What it does |
|---|---|
| `/taris-deploy-to_target` | Copy changed files to Pi, restart service, verify journal |
| `/taris-deploy-openclaw-target` | Deploy OpenClaw variant locally to TariStation2 (engineering) and remote TariStation1/SintAItion (production) or VPS-Supertaris (agents.sintaris.net, internet-facing) |
| `/taris-backup-target` | Backup a Raspberry Pi target (data, software, system config, binaries, or all) |
| `/taris-performancetest` | Run taris performance benchmarks (storage ops, menu navigation) locally and/or on Pi targets, merge results, and print a cross-platform comparison |
| `/taris-test-run-tests` | Run voice regression T01–T41 on Pi, report results |
| `/taris-run-full-tests` | Run full test suite: telegram offline, screen loader, LLM, voice regression (local + Pi), Web UI Playwright |
| `/taris-bump-version` | Update `BOT_VERSION`, prepend release note, commit |
| `/taris-test-software` | Auto-select tests based on changed files (also triggered by plain "test software") |
| `/taris-update-doc` | Sync project documentation (`doc/architecture/`, code-map, TODO, README) with current implementation |
| `/taris-test-ui` | Run Web UI Playwright + Telegram smoke tests; detect and fill coverage gaps via playwright-mcp |
| `/taris-openclaw-setup` | Setup, configure, troubleshoot, and extend the OpenClaw variant (STT, LLM, sync, tests) |
| `/taris-download-logs` | Download or tail log files (main, assistant, security, voice, datastore) from any target |
| `/taris-n8n` | Manage N8N workflows: list, create, activate, test webhooks, create campaign workflows |

📖 Full usage guide: [`doc/copilot-skills-guide.md`](../doc/copilot-skills-guide.md)

---

## Project

taris is a Raspberry Pi–based Telegram bot + offline voice assistant (Russian/German/English). Bot source lives in `src/`. The Pi target host is `OpenClawPI`. All secrets are in `.credentials/` (git-ignored).

## Reference Docs — Read on Demand

**Architecture docs are Copilot navigation maps — not textbooks. Use them to locate the right file and function, then go there. Never read an arch doc in full when you only need one section.**

| Document | When to use |
|---|---|
| [`doc/quick-ref.md`](../doc/quick-ref.md) | **Always-read first** — module map, key functions, test triggers, deploy pipeline (~3 KB) |
| [`doc/bot-code-map.md`](../doc/bot-code-map.md) | **Search, don't read whole** — grep for function name, callback key, or file name; read only the matching section. Do NOT load the full file. |
| [`doc/dev-patterns.md`](../doc/dev-patterns.md) | **Before adding any feature** — copy-paste patterns for callbacks, voice opts, multi-step flows, i18n, access guards, subprocess, session state. |
| [`doc/architecture.md`](../doc/architecture.md) | **Index only** — find the right topic file, then read only that file. Never load the index AND the topic file. |
| [`doc/research/hardware-performance-analysis.md`](../doc/research/hardware-performance-analysis.md) | Before choosing algorithms, models, or suggesting hardware upgrades. |
| [`doc/research/`](../doc/research/) | Benchmarks, LLM evals, performance reports, VPS analysis — read specific file only. |
| [`doc/test-suite.md`](../doc/test-suite.md) | **Before running or extending tests** — all test categories, run commands, trigger rules. |
| [`doc/users/roles-overview.md`](../doc/users/roles-overview.md) | Role/feature matrix, promotion paths, guest user design — before touching RBAC or access control. |
| [`TODO.md`](../TODO.md) | **Session start** — check planned/in-progress/done before proposing work. |

### Architecture Topic Files — use the right one, read only the relevant section

| Topic | File | Read when |
|---|---|---|
| System overview, variant comparison, module map | [`doc/architecture/overview.md`](../doc/architecture/overview.md) | Understanding overall structure, adding a new service |
| PicoClaw variant (Pi, Vosk, Piper, systemd) | [`doc/architecture/picoclaw.md`](../doc/architecture/picoclaw.md) | Pi-specific code, service files, audio HAT |
| OpenClaw variant (faster-whisper, Ollama, REST) | [`doc/architecture/openclaw-integration.md`](../doc/architecture/openclaw-integration.md) | OpenClaw-specific code, skill integration |
| Voice pipeline (STT/TTS/VAD/hotword) | [`doc/architecture/voice-pipeline.md`](../doc/architecture/voice-pipeline.md) | Modifying `bot_voice.py` or `voice_assistant.py` |
| Telegram bot modules, routing, callbacks | [`doc/architecture/telegram-bot.md`](../doc/architecture/telegram-bot.md) | Adding handlers, callbacks, menu buttons |
| Security, RBAC, user roles, prompt injection | [`doc/architecture/security.md`](../doc/architecture/security.md) | Modifying access logic, roles, `bot_security.py` |
| Feature domains (mail, calendar, contacts, docs) | [`doc/architecture/features.md`](../doc/architecture/features.md) | Adding or modifying user features |
| **Conversation, memory, multi-turn context, RAG** | [`doc/architecture/conversation.md`](../doc/architecture/conversation.md) | Modifying LLM call structure, history, memory, RAG injection |
| **Data layer (SQLite/Postgres, schema, stores)** | [`doc/architecture/data-layer.md`](../doc/architecture/data-layer.md) | Adding DB columns, switching backends, data file paths |
| **Software stacks (all libs, binaries, third-party)** | [`doc/architecture/stacks.md`](../doc/architecture/stacks.md) | Checking deps, upgrading packages, adding third-party tools |
| **Knowledge base (RAG, documents, KB sources)** | [`doc/architecture/knowledge-base.md`](../doc/architecture/knowledge-base.md) | Modifying RAG pipeline, document indexing, notes/calendar as KB |
| Deployment, file layout, config, backup | [`doc/architecture/deployment.md`](../doc/architecture/deployment.md) | Deploying or changing config constants |
| Multilanguage / i18n, `_t()` | [`doc/architecture/multilanguage.md`](../doc/architecture/multilanguage.md) | Adding i18n strings or a new language |
| Web UI (FastAPI, routes, auth, Screen DSL) | [`doc/architecture/web-ui.md`](../doc/architecture/web-ui.md) | Modifying `bot_web.py` or templates |
| LLM providers, multi-turn, tiered memory | [`doc/architecture/llm-providers.md`](../doc/architecture/llm-providers.md) | Modifying `bot_llm.py` or adding providers |

## Deployment Variants — Always Know Which Stack You're Working On

Taris runs on **two hardware variants** selected by `DEVICE_VARIANT` in `~/.taris/bot.env`. Before implementing any feature touching STT, LLM, storage, REST API, or voice, check which variant applies. The full reference with all packages, binaries, and env vars is in **`doc/quick-ref.md` §"Deployment Variants"** (always-read first).

| Layer | PicoClaw — Raspberry Pi | OpenClaw — x86_64 laptop/PC |
|---|---|---|
| `DEVICE_VARIANT` | `picoclaw` | `openclaw` |
| **Hosts** | OpenClawPI2 (dev) · OpenClawPI (prod) | TariStation2 · TariStation1 · VPS-Supertaris |
| **VPS-Supertaris deploy** | — | **Docker** at `/opt/taris-docker/` — NOT `~/.taris/` — see Mandatory Rules |
| **STT commands** | `vosk` (Vosk small-ru) | `faster_whisper` (CTranslate2, base/small int8) |
| **TTS** | Piper ONNX `irina-medium` | Piper ONNX `irina-medium` |
| **LLM default** | `taris` CLI → OpenRouter | `ollama` → Qwen3 local (:11434) |
| **LLM fallback** | `openai` gpt-4o-mini | `openai` gpt-4o-mini |
| **Local LLM binary** | `picoclaw` CLI / llama.cpp (:8081) | `ollama` 0.18+ (:11434) |
| **AI gateway** | ❌ | `sintaris-openclaw` Node.js (skills, MCP) |
| **Storage** | SQLite + FTS5 (`store_sqlite.py`) | PostgreSQL 14 (`store_postgres.py`) |
| **Embeddings / RAG** | sqlite-vec 384-dim | pgvector 1536-dim HNSW |
| **REST API** | ❌ | ✅ `/api/status` · `/api/chat` (Bearer) |
| **N8N** | ❌ | ✅ `bot_n8n.py` + `/webhook/n8n` |
| **OpenClaw-only packages** | — | `faster-whisper`, `scipy`, `psycopg2-binary`, `pgvector`, `sentence-transformers` |

**Variant-aware coding rules:**
- **Storage:** `get_store()` in `core/bot_db.py` returns the right adapter automatically.
- **LLM calls:** `ask_llm_with_history(chat_id, prompt)` in `core/bot_llm.py` routes per `LLM_PROVIDER`.
- **STT / voice:** guard OpenClaw-specific code with `if DEVICE_VARIANT == "openclaw"`.
- **REST endpoints:** expose new `/api/*` routes only on OpenClaw.
- **Embeddings:** pgvector `vec_embeddings` table on OpenClaw; SQLite FTS5 on PicoClaw.
- **UI parity:** Telegram UI changes must also be reflected in Web UI templates.

Full variant docs (read only the relevant section):
- [`doc/architecture/overview.md`](../doc/architecture/overview.md) — capability comparison table
- [`doc/architecture/openclaw-integration.md`](../doc/architecture/openclaw-integration.md) — OpenClaw STT/LLM/REST/pgvector details
- [`doc/architecture/picoclaw.md`](../doc/architecture/picoclaw.md) — Pi voice pipeline, systemd, hardware
- [`doc/architecture/stacks.md`](../doc/architecture/stacks.md) — full package/binary/model/service inventory

---

### Architecture Doc Style Rules (enforced when writing or updating arch docs)

These rules ensure docs stay useful as Copilot navigation tools and don't waste tokens:

1. **Tables over prose.** Every section must lead with a table (functions, files, config constants, routing rules). Prose only for decisions that can't be expressed as a table.
2. **File + function pointers are mandatory.** Every documented behaviour must reference the exact file and function name where the code lives.
3. **"When to read this file" header required.** Every `doc/architecture/*.md` file must open with a 1–2 line "When to read" statement so Copilot can decide whether to load it.
4. **No background or history.** Don't explain why something was built this way. Only document what it is and where to change it.
5. **⏳ OPEN labels for unimplemented items.** Any feature that is planned but not yet in code gets `> ⏳ **OPEN:** <one line description> → See [TODO.md §N](../TODO.md#section)`. This lets Copilot know not to rely on it.
6. **Version header must match `BOT_VERSION`.** Update `**Version:**` on every edit.
7. **Keep each topic file under 250 lines.** If a file grows beyond that, split into sub-topic files and add links from the parent.
8. **Don't duplicate.** If information lives in `bot-code-map.md`, link to it from the arch doc rather than repeating it.

## Workspace Layout

```
taris/
  src/            ← ALL target-side sources (Python, shell, services, tests)
    setup/        ← shell scripts (run on Pi)
    services/     ← systemd .service units
    tests/        ← hardware & regression tests
  backup/device/  ← sanitized Pi config snapshot
  doc/            ← architecture, code map, dev patterns
    architecture/ ← Copilot navigation maps — use with view_range, never load whole
    todo/         ← Active spec files only (1.2-guest-users, 5-voice-pipeline, 7-demo-features, 8.4-crm-platform)
    research/     ← Benchmarks, LLM evals, hardware analyses (not loaded by default)
    archive/      ← Implemented specs + old concepts (NOT for Copilot navigation)
    users/        ← User/role documentation: roles-overview.md + drawio diagrams
  .credentials/   ← secrets ONLY (never scripts or code) [gitignored]
  .env            ← all sensitive values for local use [gitignored]
  .env.example    ← variable names with placeholder values ONLY [committed]
  deploy/         ← generated deployment configs (gitignored; never commit)
```

## Skills — Use These for Specific Tasks

| Task | Skill file |
|---|---|
| Deploy bot to Pi | [bot-deploy](.github/instructions/bot-deploy.instructions.md) |
| Voice file changes | [voice-regression](.github/instructions/voice-regression.instructions.md) |
| Major update (schema/modules change) | [safe-update](.github/instructions/safe-update.instructions.md) |
| Adding/editing bot features | [bot-coding](.github/instructions/bot-coding.instructions.md) |

## Mandatory Rules

- **Secrets:** never hard-code; keep in `.credentials/.taris_env` and `.env` only.
- **Source files:** all target-side sources go in `src/`; `.credentials/` holds secrets only.
- **Version bump:** `BOT_VERSION = "YYYY.M.D"` + prepend entry in `src/release_notes.json`. Never use `\_` in JSON strings.
- **Strings:** add to all three languages (`ru`, `en`, `de`) in `src/strings.json`.
- **Service files:** always deploy to Pi in the same commit/operation as code changes. See [bot-deploy](.github/instructions/bot-deploy.instructions.md).
- **UI changes:** apply to both Telegram and Web UI simultaneously. See [bot-coding](.github/instructions/bot-coding.instructions.md).
- **Docs:** update the relevant `doc/architecture/<topic>.md` file and `README.md` in the same commit as the code change.
- **TODO.md:** keep current; collapse completed items to `✅ Implemented (vX.Y.Z)`.
- **Deployment pipeline:** ALL changes MUST be deployed and tested on the engineering target **PI2** (`OpenClawPI2`) first. Only after tests pass and the change is committed and pushed to git may it be deployed to the production target **PI1** (`OpenClawPI`). Never deploy directly to PI1 without prior PI2 validation.
- **TariStation1 (SintAItion) is a shared production VPS** — hosts PostgreSQL, N8N, Nginx, and other bots/services. ALL operations on TariStation1 (code deploy, service restarts, service file changes, package installs, database migrations, system config changes) require **explicit confirmation from the user before execution**. Present the VPS pre-checklist (see SKILL.md) before any TS1 action. Never bundle multiple TS1 operation types into a single confirmation — ask separately for each.
- **VPS-Supertaris (`agents.sintaris.net`) is a shared public internet VPS** — 🔴 HIGHEST RISK. Hosts N8N, PostgreSQL (shared DB), Nginx (reverse proxy for all bots/apps), and other services. taris runs there **in Docker** (`taris-vps-telegram`/`taris-vps-web` containers, compose project `/opt/taris-docker/`, source at `/opt/taris-docker/app/src`, config at `/opt/taris-docker/bot.env`, sub-path `/supertaris-vps/`). **NOT systemctl --user.** Deploy = copy files to `/opt/taris-docker/app/src/`, then `docker compose restart`. ALL operations require **separate explicit confirmation from the user** with the mandatory pre-VPS checklist before execution. Forbidden without confirmation: `apt upgrade/install`, Nginx config changes, PostgreSQL DDL, shared service restarts, firewall changes.
- **Continuous test improvement:** Every bug fix MUST add a regression test that would have caught the bug. Every new feature MUST add tests covering the happy path and the main failure modes. Tests live in `src/tests/test_voice_regression.py` (T-numbered) for voice/config/LLM; add new test IDs sequentially. Update `doc/test-suite.md` with the new test IDs in the same commit. No exceptions.

## Secrets & Configuration Security — MANDATORY

> **All sensitive data MUST live exclusively in `.env` (gitignored). This includes credentials, passwords, API keys, SSH keys/hostkeys, IP addresses of real hosts, usernames, database DSNs, OAuth secrets, webhook tokens, and any value that differs between environments or identifies real infrastructure.**

### Rules — enforced for every file, script, skill, prompt, and agent

1. **`.env` is the single source of truth** for all sensitive values. It is gitignored and never committed.
2. **`.env.example` documents variable names only** — placeholder values like `<your-password>` only. Safe to commit. Keep it current whenever you add a new sensitive constant.
3. **Skills, prompts, agents, and test scripts** must reference `${VAR_NAME}` or instruct the operator to source `.env` — never embed real values.
4. **Deployment scripts** (`src/setup/*.sh`, `tools/*.sh`, `tools/*.py`) must source `.env` at startup and use variables throughout. No hardcoded credentials, IPs, or passwords anywhere in committed scripts.
5. **Generated config files** (e.g. `bot.env`, `docker-compose.yml` with credentials, filled `.service` files) are produced by deployment scripts at deploy time, using `.env` as input. Save generated files to `deploy/<target>/` or a temp path — **never commit them**.
6. **Before committing any file**, verify it contains no sensitive data. Use the scan pattern:
   ```powershell
   git diff --cached | Select-String -Pattern '192\.168\.|100\.\d{2,3}\.|buerger|SHA256:|@[a-z0-9.-]+\.[a-z]{2,}|password\s*=\s*\S|token\s*=\s*\S'
   ```
7. **If a secret is accidentally committed**: immediately revoke/rotate it, then remove it from git history with `git filter-repo` or BFG.
8. **Config constants in `bot_config.py`** must always use `os.environ.get("VAR", "")` — never a real default value.

### Deployment config generation pattern

```bash
# 1. Source secrets from .env
source .env

# 2. Generate target config from template (envsubst fills ${VAR} placeholders)
mkdir -p deploy/ts2
envsubst < src/setup/templates/bot.env.template > deploy/ts2/bot.env

# 3. Copy generated config to target (never commit deploy/)
cp deploy/ts2/bot.env ~/.taris/bot.env           # TariStation2 (local)
# or via scp for remote targets

# 4. Verify no real secrets in committed templates
grep -r '\${\|{{' src/setup/templates/   # should show only placeholders
```

Template files (`src/setup/templates/*.template`) contain `${VAR_NAME}` placeholders only — safe to commit. The `deploy/` directory is gitignored.

## Post-Deploy Rule

After every successful deployment (journal shows `Version : X.Y.Z` and `Polling Telegram…`), ask:
> "Deployment verified ✅. Shall I also: 1. Commit and push to git? 2. Update `release_notes.json`?"

## Vibe Coding Protocol

After every completed request, append a row to `doc/vibe-coding-protocol.md`:
```
| HH:MM UTC | description | complexity 1–5 | N turns | model-id | files changed | done |
```

