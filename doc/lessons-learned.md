# Lessons Learned — taris

Append-only log. Newest first. See **§ Lessons Learned Protocol** in `.github/copilot-instructions.md` for rules.

| Date | Bug | Root cause | Prevention added |
|---|---|---|---|
| 2026-04-24 | "format not supported" after RTF fix deployed to VPS | Container restarted at 16:57, files deployed at 17:00 → live bot still had old in-memory code; `docker exec` tests passed (fresh subprocess) but live handler used cached imports | Deploy skills updated: always `docker compose restart` AFTER `scp`, never before. Verify with live bot action, not just `docker exec`. |
| 2026-04-24 | KB search returned 0 results after RTF document upload | `striprtf` was in `requirements.docker.txt` but not installed in the running Docker image (image built before line was added). `_extract_to_text` silently returned binary RTF → N8N parsed nothing → 0 chunks | T225 regression test added; deploy checklist updated: verify `pip show striprtf` inside container after any requirements change; added `--fail-on-missing-libs` guard in `_extract_to_text`. |
| 2026-04-24 | `_extract_to_text` swallowed ImportError and sent raw binary to N8N | `except ImportError: log.warning(); pass` silently fell through to returning raw bytes | Changed to `raise ValueError("striprtf not installed…")`. `ingest_file()` now catches and returns `{"error": str(exc)}` so the error surfaces to the user via Telegram. T227 added. |
