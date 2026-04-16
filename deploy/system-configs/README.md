# System Configs — taris Infrastructure

This directory contains all system-level configuration files and installation
scripts needed to set up, verify, or reinstall any taris deployment target.

## Structure

```
deploy/system-configs/
├── README.md                      ← this file
│
├── vps/                           ← dev2null.de VPS (agents.sintaris.net)
│   ├── install.sh                 ← full VPS setup script
│   ├── install_voice.sh           ← voice STT/TTS setup on VPS
│   ├── nginx/
│   │   └── agents.sintaris.net.conf   ← nginx reverse proxy (live config)
│   ├── docker/                    ← VPS Docker instance (Supertariss bot)
│   │   ├── Dockerfile             ← ARM64 python:3.12-slim image
│   │   ├── docker-compose.yml     ← taris-telegram + taris-web services
│   │   ├── bot.env.template       ← bot.env template (fill CHANGE_ME values)
│   │   ├── requirements.docker.txt ← lighter deps (no sounddevice/webrtcvad)
│   │   ├── deploy.sh              ← end-to-end first deploy automation
│   │   └── update.sh              ← update source + restart containers
│   ├── cron/
│   │   └── backup-taris-vps.sh   ← daily pg_dump of taris_vps DB
│   ├── systemd/
│   │   ├── sintaris-monitor.service   ← health check (every 5 min)
│   │   ├── sintaris-monitor.timer
│   │   ├── sintaris-monitor-daily.service  ← daily summary at 08:00
│   │   └── sintaris-monitor-daily.timer
│   └── postgresql/
│       ├── README.md              ← PostgreSQL setup notes
│       ├── pg_hba.conf            ← sanitized live config (replace <VPS_PUBLIC_IP>)
│       └── postgresql.conf.snippet ← key settings (non-default only)
│
├── sintaition/                    ← SintAItion (TariStation1 production)
│   ├── install.sh                 ← full SintAItion setup script
│   ├── bot.env.template           ← bot.env with CHANGE_ME placeholders
│   ├── ssh-admin-access.md        ← SSH admin tunnel setup guide
│   ├── systemd/
│   │   ├── user/                  ← systemctl --user services
│   │   │   ├── taris-telegram.service
│   │   │   ├── taris-web.service
│   │   │   ├── taris-voice.service
│   │   │   ├── taris-tunnel.service    ← autossh VPS:8086 → :8080 (/supertaris/)
│   │   │   ├── taris-pg-tunnel.service ← SSH local:15432 → VPS:5432 (CRM DB)
│   │   │   ├── ollama.service          ← user-level Ollama (legacy, disabled)
│   │   │   └── x11vnc.service          ← VNC for remote desktop
│   │   └── system/               ← sudo systemctl services
│   │       └── ollama.service    ← system-level Ollama with AMD ROCm GPU
│   └── etc/
│       └── gai.conf              ← IPv4 preference (AMD Ollama pull fix)
│
├── taristation2/                  ← TariStation2 (local engineering/dev)
│   ├── install.sh                 ← TariStation2 setup script
│   ├── bot.env.template           ← bot.env for dev/engineering target
│   └── systemd/
│       └── user/                  ← systemctl --user services
│           ├── taris-telegram.service
│           ├── taris-web.service
│           ├── taris-voice.service
│           ├── taris-tunnel.service    ← autossh VPS:8088 → :8080 (/supertaris2/)
│           └── ollama.service          ← CPU-only (no GPU flags)
│
└── pi-targets/                    ← Raspberry Pi (OpenClawPI / OpenClawPI2)
    └── README.md                  ← Pi-specific notes (service files in src/services/)
```

## Deployment Network Diagram

```
Internet
   │
   ▼
agents.sintaris.net  ←→  VPS (dev2null.de 152.53.224.213)
   │                     nginx (TLS termination)
   │                     Port tunnels:
   │                       8082 ← OpenClawPI    (/taris/)
   │                       8084 ← OpenClawPI2   (/taris2/)
   │                       8086 ← SintAItion    (/supertaris/)    ◄── ROOT_PATH in app
   │                       8088 ← TariStation2  (/supertaris2/)
   │
   ├── /taris/        → SSH reverse tunnel → OpenClawPI:8080
   ├── /taris2/       → SSH reverse tunnel → OpenClawPI2:8080
   ├── /supertaris/   → SSH reverse tunnel → SintAItion:8080     ← production
   └── /supertaris2/  → SSH reverse tunnel → TariStation2:8080   ← engineering
```

## Sub-path Routing: Two Approaches

### Approach A — nginx `sub_filter` (Pi targets, TariStation2)
Used for targets where the app does NOT know its sub-path prefix.
nginx rewrites all `href="/`, `src="/`, HTMX attributes in HTML responses.
Downside: breaks when HTML is gzip-compressed; `gzip off` required.

### Approach B — `ROOT_PATH` in app (SintAItion, recommended for new targets)
The app reads `ROOT_PATH=/supertaris` from `bot.env`.
All templates use `{{ root_path }}/path` and all redirects use `_redir()`.
nginx sets `proxy_redirect off;` — no sub_filter needed.
**Preferred for new installations.**

## Quick Verification (check installed config)

```bash
# VPS — verify tunnels and nginx
ssh stas@dev2null.de 'ss -tlnp | grep -E "808[2468]"; nginx -t'

# SintAItion — verify services
plink -batch -pw PASS -hostkey HOSTKEY stas@SintAItion.local \
  'systemctl --user status taris-web taris-telegram taris-tunnel | grep -E "Active|●"'

# All — check external access
curl -I https://agents.sintaris.net/supertaris/
```

## SSH Tunnel Keys

Each target generates its own key pair:
```bash
ssh-keygen -t ed25519 -f ~/.ssh/vps_tunnel_key -N "" -C "target-vps-tunnel"
```

Add the `.pub` to VPS `~/.ssh/authorized_keys`.

The private key path is hardcoded in `taris-tunnel.service` and `taris-pg-tunnel.service`.

## Secrets (NOT stored here)

The following must be set manually in `~/.taris/bot.env` on each target:
- `BOT_TOKEN` — from @BotFather
- `ALLOWED_USERS` / `ADMIN_USERS` — Telegram user IDs
- `OPENAI_API_KEY` — OpenAI fallback LLM
- `STORE_PG_DSN` — PostgreSQL connection string with password
- `CRM_PG_DSN` — CRM PostgreSQL (via VPS SSH tunnel)

Never commit secrets to git. They belong in `.credentials/` (gitignored) or directly in `bot.env`.

## Related Documentation

- `doc/architecture/deployment.md` — full deployment architecture
- `doc/architecture/openclaw-integration.md` — OpenClaw variant specifics
- `src/services/` — Pi target service files (Raspberry Pi variant)
- `src/setup/` — Pi and OpenClaw setup scripts
