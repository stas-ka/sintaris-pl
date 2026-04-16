# deploy/

This directory holds **generated deployment config files** produced by `src/setup/gen_config.sh`.

Files here are created from `.env` + `src/setup/templates/*.template` and contain real credentials.

**This directory is gitignored. Never commit its contents.**

Usage:
```bash
bash src/setup/gen_config.sh --target ts2   # generates deploy/ts2/bot.env etc.
```
