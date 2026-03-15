# VS Code Copilot Skills — Usage Guide

This guide explains what "skills" (prompt files) are available in this project, how Copilot loads instructions automatically, and exactly how to invoke each skill from VS Code Chat.

---

## How Copilot Instructions Work in This Project

There are **two layers** of Copilot guidance:

### Layer 1 — Auto-loaded workspace instructions
**File:** `.github/copilot-instructions.md`

This file is **loaded automatically** with every Copilot Chat request when you open this workspace in VS Code. You do **not** need to reference it in your prompts — it is always active.

It contains:
- Developer reference document table (bot-code-map, dev-patterns, architecture, etc.)
- Quick rules (versioning, callbacks, voice opts, i18n strings)
- Voice regression test table (T01–T21)
- Workspace layout and remote host access
- Post-deploy protocol

### Layer 2 — Prompt files ("skills")
**Directory:** `.github/prompts/`

These are reusable, task-specific prompt templates that you invoke **on demand**. Each file has a `description:` field shown in the VS Code picker.

---

## Available Skills

| Skill file | Invocation | What it does |
|---|---|---|
| `deploy-bot.prompt.md` | `/deploy-bot` | Copies changed files to Pi, restarts service, verifies journal |
| `run-tests.prompt.md` | `/run-tests` | Runs voice regression T01–T21 on Pi, reports pass/fail |
| `bump-version.prompt.md` | `/bump-version` | Updates `BOT_VERSION`, prepends release note, commits |
| `test-software.prompt.md` | `/test-software` | Auto-selects which tests to run based on changed files |

---

## How to Invoke a Skill in VS Code Chat

### Method 1 — Slash command (recommended)
In the VS Code Copilot Chat panel, type:
```
/deploy-bot
```
or
```
/run-tests
```
VS Code will load the matching `.prompt.md` file and execute it as an agent.

> **Requirement:** VS Code 1.99+ with `chat.promptFiles` enabled (see below).

### Method 2 — File reference
Attach the prompt file as context in your chat message:
```
#deploy-bot.prompt.md  please deploy the latest changes
```

### Method 3 — Plain text (for `test-software`)
The `test-software` skill is designed to activate automatically when Copilot sees requests like:
- "test software"
- "run tests"
- "check if everything works"

However, for guaranteed execution, use `/test-software` explicitly.

---

## Enable Prompt Files in VS Code Settings

Prompt files require VS Code 1.99+ and the following setting enabled:

1. Open **Settings** (`Ctrl+,`)
2. Search for `chat.promptFiles`
3. Enable: **Chat: Prompt Files** → ✅ `true`

Or add to `.vscode/settings.json`:
```json
{
  "chat.promptFiles": true
}
```

Once enabled, typing `/` in Copilot Chat will show all available prompts from `.github/prompts/`.

---

## Do I Need to Include Skills in My Prompts?

| Situation | What to do |
|---|---|
| General coding, bot changes, feature work | Nothing — `.github/copilot-instructions.md` is always active |
| Deploying to the Pi | Type `/deploy-bot` in Chat |
| Running tests | Type `/run-tests` or `/test-software` |
| Bumping the version | Type `/bump-version` |
| Plain text like "test software" | Works best with `/test-software`, or just say it — the auto-instructions will guide Copilot |

**Bottom line:** You only need to explicitly invoke a skill (`/skill-name`) when you want to run a specific workflow. For everyday coding assistance, the workspace instructions are always loaded and no extra prompt is needed.

---

## Adding New Skills

To add a new skill:

1. Create `.github/prompts/my-skill.prompt.md`
2. Add the frontmatter header:
   ```markdown
   ---
   mode: agent
   description: One-line description shown in VS Code picker
   ---
   ```
3. Write the step-by-step instructions in the body.
4. Add a row to the **Available Skills** table above.
5. Commit the file — it becomes available immediately in VS Code.
