# Agent Instructions — picoclaw

> For workspace and bot development instructions, see `.github/copilot-instructions.md`. For current bot state, see `AGENTS.md`.

---

## Recurring Task: Accounting 2025 (Sintaris d.o.o., Slovenia)

### Goal
Collect invoices and tax-relevant 2025 documents for preparing the 2025 tax declaration of `Sintaris d.o.o.`.

### Source
`G:\My Drive\Stas\SI\` — subfolders: `Shared_Documents`, `Antraege`, `Contracts`, `Invoices`, `additional Info`, `Reisen`, `SINTARIS`, `Bank`

### Target
`G:\My Drive\Stas\SI\accounting_2025\` — subfolders:
- `01_invoices`
- `02_bank`
- `03_contracts`
- `04_travel_slovenia_private`
- `05_tax_supporting_docs`
- `06_email_exports`

### Mail Sources
- `sintaris.com@gmail.com`
- `stanislav.ulmer@gmail.com`

### Checklist
1. Confirm source path exists.
2. Create target path and subfolders if missing.
3. Scan source for 2025-relevant files (PDF, DOCX, XLS/XLSX, CSV, images, ZIP exports).
4. Copy invoices → `01_invoices` (preserve originals).
5. Copy bank/payment confirmations → `02_bank`.
6. Copy contracts → `03_contracts`.
7. Identify private Slovenia trip documents → `04_travel_slovenia_private`.
8. Export relevant email attachments → `06_email_exports`.
9. Copy other tax-supporting records → `05_tax_supporting_docs`.
10. Generate `accounting_2025\INDEX.txt` (copied files grouped by folder).
11. Generate `accounting_2025\MISSING_ITEMS.txt` (unclear/missing docs).
12. Never store credentials in `accounting_2025`; keep secrets only in `.env`.

### Credentials
Kept in `.env` only (git-ignored). Fields: host access, `cloud.dev2null.de`, Google IMAP/SMTP app passwords, optional OAuth credentials.
