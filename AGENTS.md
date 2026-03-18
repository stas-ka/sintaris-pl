# Agent Memory — picoclaw


This file stores persistent state for AI coding agents. See `.github/copilot-instructions.md` for full workspace instructions.

## User Working Preferences
- Keep persistent operational knowledge in this file so future sessions can continue quickly.
- Use this file as the first reference for recurring document/accounting tasks.
- **Testing ("test software" / "run tests" / "verify changes"):** always read `doc/test-suite.md` first — it has the complete decision table, all run commands, and the Copilot chat-mode protocol. Never scan test files manually every session.

## Remote Host

| Key | Value |
|---|---|
| `DEV_TARGETHOST` | `OpenClawPI` |
| `DEV_HOSTUSER` | `stas` |
| `DEV_TAILSCALE_IP` | `100.81.143.126` |
| SSH | `plink -pw "%DEV_HOSTPWD%" -batch stas@OpenClawPI2 "<cmd>"` (LAN) |
| SSH remote | `plink -pw "%DEV_HOSTPWD%" -batch stas@XXX.XXX.XXX.XXX "<cmd>"` (Tailscale) |
| `PROD_TARGETHOST` | `OpenClawPI` |
| `PROD_HOSTUSER` | `stas` |
| `PROD_TAILSCALE_IP` | `100.81.143.126` |
| SSH | `plink -pw "PROD_%HOSTPWD%" -batch stas@OpenClawPI "<cmd>"` (LAN) |
| SSH remote | `plink -pw "%PROD_HOSTPWD%" -batch stas@100.81.143.126 "<cmd>"` (Tailscale) |

## Current Bot Version

`BOT_VERSION = "2026.3.25"` — deployed 2026-03-10

## Current Feature State (v2026.3.25)

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
| `Request` | One-line description |
| `Complexity` | 1 (trivial) – 5 (architecture change) |
| `Requests used` | Number of user→assistant turns |
| `Model` | Model ID from `<model_information>` tag |
| `Files changed` | Comma-separated list |
| `Status` | `done` / `partial` / `wip` |

Row format:
```
| HH:MM UTC | description | 1–5 | N turns | model-id | files | done |
```
