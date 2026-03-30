---
name: taris-update-doc
description: >
  Update project documentation after code changes, version bumps, new features,
  new skills/prompts, or any structural change. Syncs: doc/arch/*.md topic files,
  doc/bot-code-map.md, TODO.md (with links to doc/todo/ spec files), README.md,
  Copilot skill registry, Web UI route inventory, User Guide (doc/howto_bot.md),
  and in-bot Help text (strings.json help_* keys).
argument-hint: >
  Scope: all | arch | code-map | readme | todo | user-guide | help
  Optionally: list of changed files (space-separated, e.g. "src/bot_web.py src/telegram_menu_bot.py")
---

## When to Use

| Trigger | Minimal scope |
|---|---|
| Any code change merged / deployed | `all` |
| New callback or menu button added | `code-map` + `arch` |
| New FastAPI route added | `arch` (web-ui.md §17.3) + `code-map` |
| New Telegram feature / flow | `code-map` + `arch` (telegram-bot.md) |
| Version bumped (`BOT_VERSION`) | `readme` + `todo` |
| New Copilot skill / prompt added | `readme` + Copilot registry |
| TODO item completed | `todo` |
| New `doc/todo/*.md` spec file created | `todo` |
| User-facing feature added | `user-guide` + `help` |
| `strings.json` help_* keys changed | `help` |
| Architecture restructured | `arch` + `code-map` |

---

## ⚠️ Scope Selector

Read the argument (or infer from changed files) and limit work to the relevant steps:

| Scope | Steps to run |
|---|---|
| `all` | Steps 0 → 10 |
| `arch` | Steps 0, 2 |
| `code-map` | Steps 0, 3 |
| `readme` | Steps 0, 5, 6 |
| `todo` | Steps 0, 4 |
| `user-guide` | Steps 0, 8, 8b |
| `help` | Steps 0, 8, 8b, 9 |

When in doubt, run `all`.

---

## Procedure

### Step 0 — Read context and identify changed files

```
#file:doc/quick-ref.md
```

Then run:
```bat
cd /d d:\Projects\workspace\taris
git diff --name-only HEAD
```

Map each changed file to one or more documentation targets using this table:

| Changed file / area | Update target |
|---|---|
| `src/core/bot_config.py` | `doc/arch/deployment.md` §13, `doc/bot-code-map.md` §bot_config |
| `src/core/bot_state.py` | `doc/bot-code-map.md` §bot_state |
| `src/telegram/bot_access.py` | `doc/bot-code-map.md` §bot_access |
| `src/telegram/bot_admin.py` | `doc/bot-code-map.md` §bot_admin, `doc/arch/telegram-bot.md` §3.3 |
| `src/telegram/bot_handlers.py` | `doc/bot-code-map.md` §bot_handlers |
| `src/telegram/bot_users.py` | `doc/bot-code-map.md` §bot_users |
| `src/features/bot_voice.py` | `doc/arch/voice-pipeline.md`, `doc/bot-code-map.md` §bot_voice |
| `src/features/bot_calendar.py` | `doc/arch/features.md` §8, `doc/bot-code-map.md` §bot_calendar |
| `src/features/bot_contacts.py` | `doc/bot-code-map.md` §bot_contacts |
| `src/features/bot_mail_creds.py` | `doc/arch/features.md` §7, `doc/bot-code-map.md` §bot_mail_creds |
| `src/features/bot_email.py` | `doc/arch/features.md` §9, `doc/bot-code-map.md` §bot_email |
| `src/features/bot_error_protocol.py` | `doc/bot-code-map.md` §bot_error_protocol |
| `src/security/bot_security.py` | `doc/arch/security.md` §6 |
| `src/security/bot_auth.py` | `doc/arch/web-ui.md` §17.2, `doc/bot-code-map.md` §bot_auth |
| `src/core/bot_llm.py` | `doc/arch/llm-providers.md`, `doc/arch/conversation.md`, `doc/bot-code-map.md` §bot_llm |
| `src/core/bot_db.py` | `doc/arch/data-layer.md` (schema table) |
| `src/core/store*.py` | `doc/arch/data-layer.md` (backend protocol / config) |
| `src/core/bot_state.py` | `doc/arch/conversation.md` (tiered memory), `doc/bot-code-map.md` §bot_state |
| `src/telegram/bot_handlers.py` | `doc/arch/conversation.md` (message structure), `doc/bot-code-map.md` §bot_handlers |
| `src/telegram/bot_access.py` | `doc/arch/conversation.md` (system msg helpers), `doc/arch/security.md`, `doc/bot-code-map.md` §bot_access |
| `src/ui/bot_ui.py` | `doc/bot-code-map.md` §bot_ui, `doc/arch/web-ui.md` §18.2 |
| `src/ui/bot_actions.py` | `doc/bot-code-map.md` §bot_actions |
| `src/ui/render_telegram.py` | `doc/bot-code-map.md` §render_telegram |
| `src/bot_web.py` | `doc/arch/web-ui.md` §17.3, `doc/bot-code-map.md` §bot_web |
| `src/telegram_menu_bot.py` | `doc/bot-code-map.md` §callback keys, `doc/arch/telegram-bot.md` §3.4 |
| `src/strings.json` | `doc/arch/multilanguage.md` §14.3 |
| `src/core/bot_config.py` (version bump) | `README.md`, `doc/arch/deployment.md` §16 |
| New service file added | `doc/arch/deployment.md` §12, `doc/arch/overview.md` §11 |
| New Copilot skill / prompt | `.github/copilot-instructions.md`, `doc/copilot-skills-guide.md` |

---

### Step 1 — Locate sections to update

For each doc file to touch, **search for the specific section** — do not read the whole file.

```
grep_search("function_name_or_section_header", includePattern="doc/bot-code-map.md")
```

Edit only the matching section. Never rewrite prose in sections you did not touch.

---

### Step 2 — Update `doc/arch/*.md` topic files

#### ⚠️ Architecture Doc Style — MANDATORY

Architecture docs are **Copilot navigation maps**. They must remain concise, table-first, and free of prose:

| Rule | Required | Forbidden |
|---|---|---|
| Lead every section with a table | ✅ | ❌ Leading with paragraphs |
| Include file + function name for every behaviour | ✅ | ❌ "Somewhere in bot_llm.py…" |
| Mark unimplemented items `⏳ OPEN: desc → TODO.md §N` | ✅ | ❌ Describing planned features as if implemented |
| Keep file under ~250 lines | ✅ | ❌ Prose background, rationale, history |
| Open with "When to read this file" (1–2 lines) | ✅ | ❌ Missing or vague header |
| Update `**Version:**` on every edit | ✅ | ❌ Stale version header |
| Don't duplicate — link to `bot-code-map.md` instead | ✅ | ❌ Repeating function signatures already in the code map |

#### Topic → File mapping

| Topic | File | Changed by |
|---|---|---|
| System overview, variant comparison | `doc/arch/overview.md` | New service, variant flag |
| PicoClaw variant (Pi, Vosk, Piper) | `doc/arch/picoclaw.md` | Pi-specific code, HAT |
| OpenClaw variant (faster-whisper, Ollama) | `doc/arch/openclaw-integration.md` | OpenClaw code |
| Voice pipeline (STT/TTS/VAD/hotword) | `doc/arch/voice-pipeline.md` | `bot_voice.py`, `voice_assistant.py` |
| Telegram bot modules + callbacks | `doc/arch/telegram-bot.md` | New handlers, menus |
| Security, RBAC, prompt injection | `doc/arch/security.md` | Access logic, roles |
| Feature domains (mail, calendar, contacts, docs) | `doc/arch/features.md` | User features |
| **Conversation, memory, multi-turn, RAG** | `doc/arch/conversation.md` | `bot_handlers.py`, `bot_state.py`, `bot_llm.py` (history) |
| **Data layer (SQLite/Postgres, schema)** | `doc/arch/data-layer.md` | `bot_db.py`, `store*.py`, new tables |
| **Software stacks (all libs, binaries)** | `doc/arch/stacks.md` | New dependency, package upgrade, new binary |
| **Knowledge base (RAG, documents, KB sources)** | `doc/arch/knowledge-base.md` | `bot_documents.py`, RAG config, notes/calendar as KB |
| Deployment, file layout, config constants | `doc/arch/deployment.md` | Deploy changes, new constants |
| Multilanguage / i18n | `doc/arch/multilanguage.md` | `strings.json`, `_t()` |
| Web UI (FastAPI, routes, auth, Screen DSL) | `doc/arch/web-ui.md` | `bot_web.py`, templates |
| LLM providers, multi-turn, tiered memory | `doc/arch/llm-providers.md` | `bot_llm.py`, providers |

#### Update rules

- Preserve all existing structure and section numbers.
- Update the `**Version:**` header line to match the new `BOT_VERSION`.
- Add new functions/routes/flags to the relevant table; remove deleted ones.
- Do _not_ add sections that are not already in the file unless a major feature makes it unavoidable.
- If a **new** `doc/arch/*.md` topic file is created, also update `doc/architecture.md` — add a row to the Topic Index table (topic name, file link, "When to read" description).
- When adding a new `doc/arch/*.md` topic file, also add it to the Architecture Topic Files table in `.github/copilot-instructions.md`.

---

### Step 3 — Update `doc/bot-code-map.md`

This file is 39 KB. **Do not read it whole.** Search for the section you need:

```
grep_search("## modulename", includePattern="doc/bot-code-map.md")
```

For new functions: add a row to the module's function table.  
For deleted functions: remove the row.  
For new callback keys: add to the **Callback Data Key Reference** table at the bottom.  
For new routes: add to `bot_web.py` **Route inventory** table.

Update the **Architecture:** header line and `**Version:**` when the version changes.

---

### Step 4 — Update `TODO.md` and link to `doc/todo/` spec files

**Rules for `TODO.md`:**

1. Collapse all fully-implemented items to a single `✅ Implemented (vX.Y.Z)` line — never leave completed checkbox lists inline.
2. Update `🔄 In progress` items with current status.
3. For new major features, add a `🔲 Planned` item under the appropriate section.
4. Every top-level TODO item that has (or gains) a detailed spec file in `doc/todo/` **must** include a back-link:
   ```markdown
   → [Full spec](doc/todo/X.Y-feature-name.md)
   ```

**Linked spec files in `doc/todo/`:**

| Spec file | TODO section |
|---|---|
| `doc/todo/1.1-rbac.md` | §1.1 Role-Based Access Control |
| `doc/todo/1.3-developer-role.md` | §1.3 Developer Role |
| `doc/todo/4.0-contact-book.md` | §4.0 Contact Book |
| `doc/todo/5-voice-pipeline.md` | §5 Voice Pipeline |
| `doc/todo/7-demo-features.md` | §7 Demo Features |
| `doc/todo/8.4-crm-platform.md` | §8.4 CRM Platform Vision |
| `doc/todo/9-sqlite-data-layer.md` | §9 Flexible Storage Architecture |
| `doc/todo/refactor-prompts-llm.md` | LLM refactor (linked when relevant) |
| `doc/todo/storage-architecture.md` | §9 Flexible Storage Architecture |

**When creating a new spec file in `doc/todo/`:**
1. Create `doc/todo/X.Y-feature-name.md` with a matching structure (Goal, Spec, Phases, Checklist).
2. Add `→ [Full spec](doc/todo/X.Y-feature-name.md)` to the corresponding `TODO.md` section.
3. Add the file to the table above in this SKILL.md.

---

### Step 5 — Update `README.md`

Update only when:
- A new top-level feature is complete and deployed.
- `BOT_VERSION` was bumped.
- A new Copilot skill was added to `.github/prompts/`.

Do **not** rewrite existing prose. Change:
- The version badge / mentions of `BOT_VERSION`.
- The feature list bullets (add new feature; do not remove old ones unless deprecated).
- The Copilot Skills table if a new skill was added.

---

### Step 6 — Update Copilot skill registry

When a new prompt or skill is added:

**File 1:** `.github/copilot-instructions.md` — Available Skills table:
```markdown
| `/new-skill` | One-line description of what it does |
```

**File 2:** `doc/copilot-skills-guide.md` — Available Skills table:
```markdown
| `new-skill.prompt.md` | `/new-skill` | One-line description |
```

Both tables must stay in sync.

---

### Step 7 — Update Web UI route inventory (`doc/arch/web-ui.md` §17.3)

When `src/bot_web.py` gains or loses routes:

Open `doc/arch/web-ui.md`, find the `### 17.3 Route Inventory` table, and add/remove rows:

```markdown
| `METHOD` | `/path` | Description | Auth |
```

Auth column values: `—` (public) · `✅` (user) · `✅ admin` (admin only).

---

### Step 8 — Update User Guide (`doc/howto_bot.md`)

Update when a user-facing feature is added, changed, or renamed.

Rules:
- Add a new section `## N. Feature Name` for any new top-level feature.
- Update existing sections if menu text, button labels, or flow steps changed.
- Keep examples (example messages, button presses) up to date.
- Match the voice and tone of existing sections (concise, present-tense instructions).
- Do _not_ add implementation details — this is a user guide, not a technical reference.

Check `doc/howto_bot.md` sections against the current menu structure in `src/telegram/bot_access.py` (`_menu_keyboard`) and `src/telegram_menu_bot.py`.

---

### Step 8b — Playwright verification (mandatory)

When a user-facing Web UI change is documented, verify that all documented routes are live before committing.

1. Confirm the test target is PI2:
   ```bat
   type src\tests\ui\conftest.py | findstr "base_url"
   ```
2. Run the full Web UI test suite:
   ```bat
   py -m pytest src/tests/ui/test_ui.py -v --base-url https://openclawpi2:8080 --browser chromium
   ```
3. If any test fails:
   - `404` / `500` on a documented route → update the route entry in Step 7 **or** fix the route in `src/bot_web.py` before documenting it.
   - Assertion mismatch on a heading or label → correct `doc/howto_bot.md` (Step 8) and `src/strings.json` (Step 9) to match the actual UI.
   - All failures must be resolved before the `git commit` in Step 11.

> **Skip only if** no Web UI routes or templates were changed (e.g. a pure voice-pipeline or Telegram-only change).

---

### Step 9 — Update in-bot Help text (`strings.json` help keys)

When new features are added or renamed:

1. Open `src/strings.json` and search for help keys:
   ```
   grep_search("help_", includePattern="src/strings.json")
   ```
2. Update `help_text`, `help_text_admin`, `help_text_guest` in **all three languages** (`ru`, `en`, `de`).
3. Add new feature mentions at the appropriate role level:
   - `help_text_guest` — guest-accessible features only
   - `help_text` — all approved-user features
   - `help_text_admin` — admin-only additions
4. For any new user-facing feature, include a reference to the full User Guide in the help text:
   ```
   📖 Подробнее: /help_guide  (ru)
   📖 More info: /help_guide  (en)
   📖 Mehr Info: /help_guide  (de)
   ```
   Link or point to the relevant section in `doc/howto_bot.md`.
5. Validate the JSON after editing (Step 10).

---

### Step 10 — Validate JSON files

After any change to `src/strings.json` or `src/release_notes.json`:

```bat
python3 -c "import json,sys; json.load(sys.stdin)" < src/strings.json
python3 -c "import json,sys; json.load(sys.stdin)" < src/release_notes.json
```

Both must return with no output (exit code 0).

Also verify `strings.json` key coverage:
```bat
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "python3 /home/stas/.taris/tests/test_voice_regression.py --test i18n"
```
All three languages must have identical key sets (T13).

---

### Step 11 — Git commit docs

Stage and commit all documentation changes:

```bat
cd /d d:\Projects\workspace\taris
git add doc/ README.md TODO.md src/strings.json .github/copilot-instructions.md .github/prompts/ .github/skills/
git commit -m "docs: sync documentation with vX.Y.Z changes"
```

Use `docs:` commit prefix for documentation-only changes.  
Use `feat: <feature> + docs:` for commits that include both code and documentation.

---

## Pass / Fail Rules

| Check | Pass | Fail — action |
|---|---|---|
| `strings.json` parses | `python3 -c "import json,sys; json.load(sys.stdin)" < src/strings.json` exits 0 | Fix JSON syntax error before committing |
| `release_notes.json` parses | Same check | Fix JSON syntax error |
| T13 i18n key coverage | All 3 languages have identical key sets | Add missing keys to `ru`, `en`, `de` |
| No raw hardcoded bot name in changed doc | No "PicoClaw" / "taris" in user-facing text (use `{bot_name}`) | Replace with `{bot_name}` placeholder |
| `TODO.md` has no stale completed items | All `[x]` bullets collapsed to `✅ Implemented (vX.Y.Z)` | Collapse to one line |
| All `doc/todo/*.md` spec files linked | Every spec file has a `→ [Full spec]()` back-link in `TODO.md` | Add missing back-link |
| `doc/arch/` version headers updated | All edited topic files have updated `**Version:**` | Update version line |
| `doc/bot-code-map.md` callback table complete | Every callback key in `telegram_menu_bot.py` has a row in the table | Add missing rows |
| User Guide matches current menu | `doc/howto_bot.md` sections match `_menu_keyboard()` in `bot_access.py` | Update mismatched sections |
| Help text present in all 3 languages | `help_text*` keys exist in `ru`, `en`, `de` in `strings.json` | Add missing translations |
| Playwright tests pass (Web UI changes) | All `test_ui.py` assertions pass against PI2 | Fix route/label mismatch before committing |
| `doc/architecture.md` index updated | Every `doc/arch/*.md` file has a row in the index table | Add missing row to Topic Index |
| Git diff is clean after commit | `git status` shows no unstaged changes in `doc/` or tracked doc files | Stage and commit missing files |
