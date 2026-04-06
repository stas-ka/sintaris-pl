---
name: taris-bump-version
description: >
  Bump BOT_VERSION in bot_config.py, prepend a new entry to release_notes.json,
  and commit. Run after every user-visible change.
argument-hint: >
  Optional: version string (YYYY.M.D). If omitted, uses today's date.
  Optional: title (short feature name for release note).
---

## When to Use

Run this skill every time a user-visible change is released:
- New feature deployed
- Bug fix deployed
- Configuration change affecting user experience

---

## Step 1 — Update BOT_VERSION

File: `src/core/bot_config.py`

Find:
```python
BOT_VERSION = "YYYY.M.D"
```
Replace with today's date in `YYYY.M.D` format — **no leading zeros** (e.g. `2026.3.1`, not `2026.03.01`).

---

## Step 2 — Prepend entry to `src/release_notes.json`

Add a new JSON object at the **top** of the array (position 0):

```json
{
  "version": "2026.3.15",
  "date":    "2026-03-15",
  "title":   "Short feature name",
  "notes":   "- Bullet 1\n- Bullet 2"
}
```

**Rules:**
- Never use `\_` (backslash-underscore) in the `notes` string — invalid JSON escape.
- Keep all existing entries below; never delete or modify them.
- `date` format: `YYYY-MM-DD` (ISO 8601).
- `title`: one concise noun phrase, no punctuation at end.

---

## Step 3 — Validate JSON

```bash
python3 -c "import json,sys; json.load(sys.stdin)" < src/release_notes.json
python3 -c "import json,sys; json.load(sys.stdin)" < src/strings.json
```
Both must exit 0 (no output).

---

## Step 4 — Commit

```bash
git add src/core/bot_config.py src/release_notes.json
git commit -m "chore: bump version to 2026.3.15

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Step 5 — Deploy (if ready)

If deploying immediately, run `/taris-deploy-to-target` next.

After deploy, verify in the journal:
```
[INFO] Version      : 2026.3.15
[INFO] Polling Telegram…
```

---

## Pass / Fail Rules

| Check | Pass | Fail |
|---|---|---|
| `release_notes.json` parses | exit 0 | Fix JSON before committing |
| No `\_` in notes string | Not present | Replace with plain `_` |
| `BOT_VERSION` matches release notes | Identical date string | Fix mismatch |
| Journal after deploy shows new version | `Version : 2026.3.15` | Redeploy / restart service |
