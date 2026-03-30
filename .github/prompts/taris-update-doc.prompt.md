---
mode: agent
description: Sync project documentation with the current implementation — update doc/architecture/, bot-code-map, README, and TODO.md after any code changes.
---

# Update Documentation (`/taris-update-doc`)

**Usage**: `/taris-update-doc [scope]`

| Parameter | Values | Default |
|---|---|---|
| `scope` | `all` \| `arch` \| `code-map` \| `readme` \| `todo` \| `web-ui` | `all` |

---

## Read context first

Before executing any step, read:
1. `doc/quick-ref.md` — module map and key files
2. `doc/architecture.md` — index of topic files under `doc/architecture/`

---

## Step 0 — Identify changed files

```bat
rem List files changed since last commit
git -C "d:\Projects\workspace\taris" diff --name-only HEAD

rem Or since a specific version tag
git -C "d:\Projects\workspace\taris" diff --name-only HEAD~1
```

Use the output to determine which documentation areas are affected.

---

## Step 1 — Map changed source files to documentation

| Changed source file / area | Documentation to update |
|---|---|
| `src/core/bot_config.py` | `doc/architecture/deployment.md` §13 (constants table) |
| `src/core/bot_state.py` | `doc/bot-code-map.md` (bot_state section) |
| `src/core/bot_llm.py` | `doc/architecture/llm-providers.md`, `doc/bot-code-map.md` |
| `src/security/bot_security.py` | `doc/architecture/security.md` |
| `src/security/bot_auth.py` | `doc/architecture/web-ui.md` §17.2, `doc/bot-code-map.md` |
| `src/telegram/bot_access.py` | `doc/bot-code-map.md` (bot_access section) |
| `src/telegram/bot_admin.py` | `doc/bot-code-map.md`, `doc/architecture/telegram-bot.md` §3.3 |
| `src/telegram/bot_handlers.py` | `doc/bot-code-map.md` |
| `src/telegram/bot_users.py` | `doc/bot-code-map.md` |
| `src/features/bot_voice.py` | `doc/architecture/voice-pipeline.md` §5 |
| `src/features/bot_calendar.py` | `doc/architecture/features.md` §8, `doc/bot-code-map.md` |
| `src/features/bot_contacts.py` | `doc/architecture/features.md`, `doc/bot-code-map.md` |
| `src/features/bot_mail_creds.py` | `doc/architecture/features.md` §7 |
| `src/features/bot_email.py` | `doc/architecture/features.md` §9 |
| `src/ui/bot_actions.py` | `doc/architecture/web-ui.md` §18.3, `doc/bot-code-map.md` |
| `src/ui/render_telegram.py` | `doc/architecture/web-ui.md` §18.4 |
| `src/ui/bot_ui.py` | `doc/architecture/web-ui.md` §18.2 |
| `src/bot_web.py` | `doc/architecture/web-ui.md` §17.3 (route inventory), `doc/bot-code-map.md` |
| `src/telegram_menu_bot.py` | `doc/bot-code-map.md` (callback key table) |
| `src/strings.json` | `doc/architecture/multilanguage.md` §14.3 (key count) |
| `src/release_notes.json` | `README.md` (version badge / changelog section) |
| `.github/prompts/*.prompt.md` | `doc/copilot-skills-guide.md`, `.github/copilot-instructions.md` §Available Skills |
| `src/tests/ui/test_ui.py` | `doc/test-suite.md` §3 (Web UI test classes table) |
| `src/tests/test_voice_regression.py` | `doc/test-suite.md` §2 (voice regression table) |
| `src/core/store_sqlite.py` | `doc/architecture/deployment.md`, `doc/todo/storage-architecture.md` |

---

## Step 2 — Update architecture docs (`doc/architecture/`)

For each affected `doc/architecture/<topic>.md` file:

1. Read the current content of the file.
2. Identify sections that describe the **changed functionality**.
3. Update function tables, constant tables, or route inventories to reflect the new implementation.
4. Update the `**Version:**` header to `BOT_VERSION` from `src/core/bot_config.py`.

**Key rules:**
- Preserve the exact section structure — numbered headings, tables, and fenced code blocks.
- Only update sections that describe the changed functionality. Leave unrelated sections untouched.
- Do NOT rewrite or summarise entire files.

---

## Step 3 — Update `doc/bot-code-map.md`

`doc/bot-code-map.md` is a 39 KB map. **Do not read the whole file — search for the specific section.**

For each changed module, search the file for the module name (e.g. `bot_contacts.py`) and update:
- The **Module Overview** table row (lines count, responsibility)
- The **per-module function table** — add new functions, remove deleted ones, update descriptions
- The **Callback Data Key Reference** table — add/remove `data=` keys handled in `callback_handler()`

```python
# Pattern: search for the section header in the code map
# grep: "## bot_contacts.py"
```

---

## Step 4 — Update `TODO.md`

1. Read `TODO.md`.
2. For any just-implemented feature, collapse the `- [ ]` bullets into one line:
   ```markdown
   ✅ Implemented (vX.Y.Z)
   ```
   Remove the interior bullet list (keep only the summary line).
3. Update any `🔄 In progress` entries if their status changed.
4. Do NOT add new entries — only collapse completed work.

---

## Step 5 — Update `README.md`

Only update `README.md` if:
- A new top-level feature was added (visible to end users)
- The version changed
- A new Copilot skill was added

Do NOT add prose or rewrite existing sections.

---

## Step 6 — Update Copilot skill registry (if new skills added)

If a new `.github/prompts/*.prompt.md` file was added or renamed:

1. Open `.github/copilot-instructions.md`.
2. Find the **Available Skills** table near the top.
3. Add a new row with: `| /skill-name | What it does |`

4. Open `doc/copilot-skills-guide.md`.
5. Add a row to the **Available Skills** table there too.

---

## Step 7 — Update Web UI route inventory in `doc/architecture/web-ui.md`

If `src/bot_web.py` changed, verify the route inventory in §17.3 is accurate:

```python
# Scan bot_web.py for route decorators
# grep: ^@app\.(get|post|put|delete|patch)
```

Add any new routes. Remove routes that were deleted. Update descriptions.

---

## Step 8 — Verify documentation against live UI (optional, requires playwright-mcp)

If the Web UI changed, use playwright-mcp to confirm that documented routes and UI elements are actually present.

```
# Load playwright-mcp tools (search for "playwright" in tool registry)
# Then:
# 1. Navigate to https://openclawpi2:8080/login
# 2. Take a snapshot of the current DOM
# 3. Compare menu items and headings against doc/architecture/web-ui.md §17.3
# 4. Note any routes or sections present in the live UI but missing from docs
```

**Use playwright for live verification only. Never modify tests here.**
Do not edit `src/tests/ui/test_ui.py` in this skill — use `/taris_test_ui` for that.

---

## Step 9 — Validate JSON files

After any changes to `src/strings.json` or `src/release_notes.json`:

```bat
python -c "import json,sys; json.load(open('src/strings.json'))" && echo strings.json OK
python -c "import json,sys; json.load(open('src/release_notes.json'))" && echo release_notes.json OK
```

---

## Step 10 — Commit documentation changes

```bat
git -C "d:\Projects\workspace\taris" add doc/ README.md TODO.md .github/
git -C "d:\Projects\workspace\taris" commit -m "docs: sync with v$(python -c \"import sys; sys.path.insert(0,'src'); import importlib.util; spec=importlib.util.spec_from_file_location('bc','src/core/bot_config.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print(m.BOT_VERSION)\")"
```

Or provide the version explicitly:
```bat
git -C "d:\Projects\workspace\taris" commit -m "docs: sync with v2026.X.Y implementation"
```

---

## Pass/Fail rules

| Check | Pass | Action on Fail |
|---|---|---|
| All modified `doc/architecture/*.md` files updated | Version header matches `BOT_VERSION` | Update `**Version:**` header |
| `bot-code-map.md` function tables accurate | All functions present in code appear in map | Add missing functions; remove deleted ones |
| `TODO.md` completed items collapsed | No dangling `- [x]` items without `✅ Implemented` | Collapse using format above |
| `strings.json` valid JSON | `python -c "..."` returns OK | Fix JSON syntax — never use `\_` |
| `release_notes.json` valid JSON | `python -c "..."` returns OK | Fix JSON syntax |
| Web UI routes in docs match `bot_web.py` | No undocumented `@app.*` decorators | Add missing route rows to §17.3 |

---

## Quick scopes

| Scope | Steps to run |
|---|---|
| `arch` | Steps 0, 1, 2, 4 |
| `code-map` | Steps 0, 1, 3 |
| `readme` | Steps 0, 5 |
| `todo` | Steps 0, 4 |
| `web-ui` | Steps 0, 7, 8 |
| `all` | All steps |
