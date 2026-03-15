---
mode: agent
description: Bump BOT_VERSION, prepend a new entry to release_notes.json, and commit.
---

# Bump Bot Version

Follow these steps every time a user-visible change is released.

## Step 1 — Update BOT_VERSION in `src/telegram_menu_bot.py`

Find the line:
```python
BOT_VERSION = "YYYY.M.D"
```
Replace with today's date in `YYYY.M.D` format (no leading zeros, e.g. `2026.3.1`).

## Step 2 — Prepend entry to `src/release_notes.json`

Add a new object at the **top** of the JSON array. Never use a backslash followed by an underscore (`\_`) in the notes string — that is an invalid JSON escape sequence:

```json
{
  "version": "2026.3.15",
  "date":    "2026-03-15",
  "title":   "Short feature name",
  "notes":   "- Bullet 1\n- Bullet 2"
}
```

Keep all existing entries below it.

## Step 3 — Commit

```
git add src/telegram_menu_bot.py src/release_notes.json
git commit -m "chore: bump version to 2026.3.15"
```

## Step 4 — Deploy (optional)

If ready to deploy immediately, run the **deploy-bot** skill next:
> Use prompt: `deploy-bot`

## Validation

After deploy, confirm in the journal:
```
[INFO] Version      : 2026.3.15
```
And that the admin receives an in-chat release notification (once per `BOT_VERSION`).
