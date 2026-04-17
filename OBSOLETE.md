# Taris Bot — Obsolete / Cancelled Items

> Items moved here from `TODO.md` that will **not** be implemented.
> Reason documented for each: either superseded by another feature, hardware not viable, or cancelled.

---

## §17 Implementing Max Messenger UI analog Telegram ❌ Cancelled

**Original goal:** Add a Max messenger client/bot as an alternative to Telegram.

**Reason cancelled:** The Web UI (FastAPI + Jinja2, `src/bot_web.py`) fulfils the same need —
a browser-based interface accessible from any device without Telegram. Building a Max messenger
integration would duplicate the Web UI with no measurable gain for the current user base.

**Superseded by:** §21 Web UI (`src/bot_web.py`, `src/web/templates/`) — fully implemented.

---

## §18 Using ZeroClaw Instead PicoClaw ❌ Not viable

**Original goal:** Deploy taris on a ZeroClaw device (e.g. Raspberry Pi Zero 2 W, 512 MB RAM)
as a minimal/ultra-low-cost hardware variant.

**Reason cancelled:** Hardware analysis (v2026.3.26) confirmed that 512 MB RAM is insufficient
for the full taris voice stack:
- Vosk 0.22 model alone requires ~220 MB RAM
- Piper TTS binary + model requires ~150 MB RAM
- Python bot process overhead ~200 MB
- Total: ~570 MB — exceeds the device limit

Text-only mode is theoretically possible but provides no voice capability, making it a
degraded experience not worth maintaining a separate hardware variant.

**Reference:** [Hardware Requirements Report §4.2](doc/hw-requirements-report.md)

**Alternative:** Use PicoClaw (Pi 4 B 2GB+) for minimal deployments, or OpenClaw (Pi 5 8GB)
for full stack including local LLM.

---
