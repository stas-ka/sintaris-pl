# Taris — Admin & Operator Guide

**Version:** `2026.4.24`  
**Applies to:** OpenClaw variant (`taris-openclaw` branch)  
**Targets:** TariStation2 (engineering) · SintAItion / TariStation1 (production)  
**User guide:** [howto_bot.md](howto_bot.md) · **Install guide:** [install-new-target.md](install-new-target.md)

---

## 1. Quick Reference

| Task | Command |
|---|---|
| Restart bot | `systemctl --user restart taris-telegram taris-web` |
| Check status | `systemctl --user status taris-telegram taris-web` |
| Live logs | `journalctl --user -u taris-telegram -f` |
| Check memory | `free -m` |
| Check swap | `swapon -s` |
| Bot version | `grep BOT_VERSION ~/.taris/core/bot_config.py` |
| Sync source → deploy | See §5 Deployment |
| SSH to SintAItion (home) | `ssh stas@192.168.178.175` or `ssh stas@SintAItion` |
| SSH to SintAItion (internet) | `ssh stas@100.112.120.3` (Tailscale) |
| Switch to remote deploy mode | `source tools/use_tailscale.sh` |
| Switch to LAN deploy mode | `source tools/use_lan.sh` |

---

## 2. Target Comparison

Both targets run `DEVICE_VARIANT=openclaw` (`taris-openclaw` branch) but differ in hardware, memory, and performance profile.

### Hardware Summary

| Property | TariStation2 | SintAItion (TariStation1) |
|---|---|---|
| **Role** | Engineering / dev | Production |
| **Branch** | `taris-openclaw` (any) | `taris-openclaw` (master-equivalent) |
| **CPU** | Intel i7-2640M (dual-core, 2011) | x86_64 (modern) |
| **RAM** | 7.6 GB | ≥ 16 GB |
| **Swap** | 512 MB | Adequate |
| **GPU** | None | AMD Radeon 890M (gfx1150, RDNA3.5, 16 GB VRAM) |
| **GPU driver** | — | ROCm (via Ollama libs) |
| **Storage** | SSD | SSD |
| **Hostname** | `TariStation2` / `IniCoS-1` | `SintAItion` / `SintAItion.local` |
| **Network** | LAN (home) | LAN + Tailscale (`100.112.120.3`) |
| **Services sharing host** | Ollama, Copilot CLI, Telegram Desktop, Firefox, n8n | Ollama only |

### Software Configuration Summary

| Setting | TariStation2 | SintAItion |
|---|---|---|
| `DEVICE_VARIANT` | `openclaw` | `openclaw` |
| `LLM_PROVIDER` | `openai` (gpt-4o-mini) | `ollama` (qwen3.5:9b) |
| `LLM_FALLBACK_PROVIDER` | `ollama` | `openai` |
| `OLLAMA_MODEL` | `qwen3.5:0.8b` (fast, CPU) | `qwen3.5:latest` (9B, GPU) |
| `STT_PROVIDER` | `faster_whisper` | `faster_whisper` |
| `FASTER_WHISPER_MODEL` | `small` | `small` |
| `FASTER_WHISPER_PRELOAD` | **`0`** ← disabled | **`1`** ← enabled |
| `FASTER_WHISPER_DEVICE` | `cpu` | `cpu` |
| `FASTER_WHISPER_COMPUTE` | `int8` | `int8` |
| `STORE_BACKEND` | `postgres` | `postgres` |
| `ROOT_PATH` | `/supertaris2` | `/` (or configured path) |
| Bot name | `Taris2` | `Taris` |
| LLM latency | ~1.5–8 s (cloud) | ~1.2 s (local GPU) |
| STT cold start | **3–5 s** (lazy load) | < 0.1 s (preloaded) |

> ⚠️ **`FASTER_WHISPER_PRELOAD=0` on TariStation2 is critical.** The `small` model consumes ~460 MB RAM when preloaded. TariStation2 only has 512 MB swap and shares RAM with Ollama (~2 GB), Copilot CLI (~780 MB), Telegram Desktop (~476 MB), Firefox. Without this setting, swap exhausts and all callback handlers stall for 30–107 seconds. See [performance-report-2026-04-02.md](performance-report-2026-04-02.md).

---

## 3. bot.env Reference

All configuration lives in `~/.taris/bot.env`. This file is **never committed to git** — it holds secrets and machine-specific settings.

### Complete Reference (OpenClaw variant)

```ini
# ── Core — Telegram ──────────────────────────────────────────────────────────
BOT_TOKEN=<telegram_bot_token>         # From @BotFather
ALLOWED_USERS=<chat_id>               # Comma-separated Telegram chat IDs
ADMIN_USERS=<chat_id>                 # Admin chat IDs (defaults to ALLOWED_USERS)
DEVELOPER_USERS=<chat_id>             # Developer-role users (optional)
BOT_NAME=Taris                        # Display name in UI

# ── Deployment variant ────────────────────────────────────────────────────────
DEVICE_VARIANT=openclaw               # picoclaw | openclaw

# ── LLM provider ─────────────────────────────────────────────────────────────
LLM_PROVIDER=ollama                   # openai | ollama | gemini | anthropic | taris
LLM_FALLBACK_PROVIDER=openai          # Fallback if primary fails
LLM_LOCAL_FALLBACK=1                  # 1 = try ollama if primary fails

# ── OpenAI / cloud LLM ───────────────────────────────────────────────────────
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini

# ── Ollama (local LLM) ───────────────────────────────────────────────────────
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3.5:latest           # TariStation2: qwen3.5:0.8b | SintAItion: qwen3.5:latest
OLLAMA_MIN_TIMEOUT=90                 # Prevents cold-load timeouts for large models
OLLAMA_THINK=false                    # REQUIRED for qwen3 — without this, empty responses

# ── Voice — STT (Speech-to-Text) ─────────────────────────────────────────────
STT_PROVIDER=faster_whisper
STT_LANG=ru                           # ru | en | de
FASTER_WHISPER_MODEL=small            # tiny | base | small | medium
FASTER_WHISPER_DEVICE=cpu             # cpu | cuda (use cpu even on AMD GPU — ROCm via compat)
FASTER_WHISPER_COMPUTE=int8           # int8 (recommended for CPU)
FASTER_WHISPER_PRELOAD=1              # 0 = lazy-load (REQUIRED on TariStation2!)
                                      # 1 = preload at startup (OK on SintAItion)

# ── Voice — TTS (Text-to-Speech) ─────────────────────────────────────────────
PIPER_BIN=~/.taris/piper/piper
PIPER_MODEL=~/.taris/ru_RU-irina-medium.onnx
PIPER_MODEL_DE=~/.taris/de_DE-thorsten-medium.onnx  # Optional: German TTS

# ── Storage ───────────────────────────────────────────────────────────────────
STORE_BACKEND=postgres
STORE_PG_DSN=postgresql://taris:taris_openclaw_2026@localhost:5432/taris

# ── Web UI ────────────────────────────────────────────────────────────────────
WEB_HOST=0.0.0.0
WEB_PORT=8080
WEB_SECRET_KEY=<random-hex-64-chars>
ROOT_PATH=/supertaris2                # URL prefix (empty = served at /)
TARIS_API_TOKEN=<random-hex-64-chars> # REST API bearer token

# ── RAG / Knowledge Base ─────────────────────────────────────────────────────
RAG_ENABLED=1
RAG_TOP_K=3
RAG_CHUNK_SIZE=512

# ── Network (optional tuning) ─────────────────────────────────────────────────
# CONNECT_TIMEOUT=15                  # seconds (default)
# READ_TIMEOUT=10                     # seconds (reduced from 30 — fixes stale TCP)

# ── Optional integrations ────────────────────────────────────────────────────
NEXTCLOUD_URL=https://cloud.example.com
NEXTCLOUD_USER=<username>
NEXTCLOUD_PASS=<app-password>
NEXTCLOUD_REMOTE=/TarisBackups
```

---

## 4. Memory Management

### Why Memory Matters

Taris runs on machines that may share RAM with other processes (Ollama, IDE, browser). Memory pressure causes kernel page-fault stalls — the single most common cause of Telegram callback freezes.

### Memory Footprint by Component

| Component | RSS | Notes |
|---|---|---|
| Bot (no preload) | ~70 MB | Python + bot modules only |
| Bot (small model preloaded) | ~530 MB | +460 MB for FasterWhisper small |
| Ollama — qwen3.5:0.8b | ~512 MB | Good for CPU-only machines |
| Ollama — qwen3.5:9b | ~2.0 GB | GPU machine recommended |
| PostgreSQL | ~50–100 MB | |
| Piper TTS (per call) | ~50 MB | Released after synthesis |

### Startup Memory Warning

The bot logs a warning at startup if memory is dangerously low:

```
[startup] LOW MEMORY: only 312 MB available — callbacks may stall
[startup] HIGH SWAP: 97% used — risk of page-fault stalls
```

If you see these warnings, check which processes are consuming RAM (`htop`, `ps aux --sort=-%mem`) and reduce load before the bot is usable.

### Swap Recommendations

| Machine type | Recommended swap |
|---|---|
| Dedicated Taris server | 4–8 GB (SSD swap or RAM) |
| Dev machine shared with Ollama | ≥ 4 GB swap, OR set `FASTER_WHISPER_PRELOAD=0` |
| Pi 4 (2 GB RAM) | 2 GB swap file on SSD |

---

## 5. Deployment

### Deploy Source → TariStation2 (local)

```bash
# Sync all commonly-changed files
cp src/core/bot_config.py          ~/.taris/core/
cp src/core/bot_llm.py             ~/.taris/core/
cp src/core/bot_logger.py          ~/.taris/core/
cp src/features/bot_voice.py       ~/.taris/features/
cp src/bot_web.py                  ~/.taris/
cp src/telegram_menu_bot.py        ~/.taris/
cp src/strings.json src/release_notes.json ~/.taris/

# Web templates + static (if changed)
cp src/web/templates/*.html        ~/.taris/web/templates/
cp src/web/static/*                ~/.taris/web/static/

# Restart
systemctl --user restart taris-telegram taris-web

# Verify (version in log)
journalctl --user -u taris-telegram -n 5 --no-pager | grep Version
```

### Verify Sync (before restart)

```bash
for f in src/bot_web.py src/core/bot_config.py src/core/bot_llm.py src/features/bot_voice.py; do
  diff "$f" ~/.taris/"${f#src/}" > /dev/null 2>&1 && echo "OK $f" || echo "DIFF $f (NOT SYNCED)"
done
diff -rq src/web/templates ~/.taris/web/templates && echo "OK templates" || echo "DIFF templates"
```

### Deploy to SintAItion (remote)

```bash
source .env  # loads OPENCLAW1_HOST, OPENCLAW1_USER, OPENCLAW1PWD

sshpass -p "$OPENCLAW1PWD" scp -o StrictHostKeyChecking=no \
  src/core/bot_config.py src/core/bot_llm.py src/core/bot_logger.py \
  stas@SintAItion.local:~/.taris/core/

sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no stas@SintAItion.local \
  "systemctl --user restart taris-telegram taris-web && sleep 3 && \
   journalctl --user -u taris-telegram -n 5 --no-pager"
```

### Deployment Pipeline Rule

**Always deploy to TariStation2 first. Deploy to SintAItion only after tests pass.**

```
TariStation2 (dev) → run tests → commit + push → SintAItion (production)
```

---

## 6. Service Management

### Services on OpenClaw targets

```bash
# Status
systemctl --user status taris-telegram taris-web

# Restart
systemctl --user restart taris-telegram taris-web

# Logs (live)
journalctl --user -u taris-telegram -f

# Last 50 lines
journalctl --user -u taris-telegram -n 50 --no-pager

# Find errors
journalctl --user -u taris-telegram --since "1 hour ago" | grep -i "error\|warn\|perf"
```

### Performance Warning — PERF log lines

The bot logs callback timing with the `PERF` prefix. Any PERF value over 1000 ms indicates a problem:

```
PERF [menu_calendar]  423 ms   ← OK
PERF [menu_calendar]  107056 ms ← CRITICAL: swap exhaustion
```

Check memory immediately when you see PERF values > 5000 ms:
```bash
free -m
ps aux --sort=-%mem | head -10
```

### Ollama Service (SintAItion)

```bash
# Status
systemctl status ollama

# Restart
sudo systemctl restart ollama

# Check GPU offload (should show 41/41 layers for qwen3.5:9b)
journalctl -u ollama -n 20 --no-pager | grep -i "offload\|layer\|gpu"
```

---

## 7. Network Configuration

### SintAItion — Network Fixes Applied (2026-03-31)

SintAItion had intermittent connectivity due to:
1. **Energy Efficient Ethernet (EEE)** causing NIC carrier drops
2. **Route metric misconfiguration** (traffic used wrong interface)
3. **IPv6 preference** in Go DNS resolver (Ollama model downloads failed)

**Permanent fixes applied:**

```bash
# /etc/network/interfaces or via netplan — disable EEE on eth0
# (must survive reboots — add to /etc/rc.local or systemd)
ethtool --set-eee eth0 eee off

# Route metrics (lower = preferred):
ip route change default via <gateway> dev eth0 metric 101      # wired LAN preferred
ip route change default via <gateway> dev wifi0 metric 200
ip route change default via <gateway> dev tailscale0 metric 300

# /etc/gai.conf — prefer IPv4 for Go resolver
precedence ::ffff:0:0/96  100
```

Ollama systemd service (`/etc/systemd/system/ollama.service`):
```ini
[Service]
Environment=HSA_OVERRIDE_GFX_VERSION=11.0.3
Environment=LD_LIBRARY_PATH=/usr/local/lib/ollama/rocm
Environment=GODEBUG=netdns=cgo
```

### TCP Keepalive & Timeout (Both Targets)

The Telegram bot uses `READ_TIMEOUT=10s` and `CONNECT_TIMEOUT=15s`. These are set in `bot_config.py`:

```python
CONNECT_TIMEOUT = int(os.environ.get("CONNECT_TIMEOUT", "15"))
READ_TIMEOUT    = int(os.environ.get("READ_TIMEOUT",    "10"))
```

The reduced `READ_TIMEOUT=10s` (previously 30s) ensures stale TCP connections to `api.telegram.org` are detected quickly (important behind FritzBox/NAT that drops idle connections after 60s).

---

## 8. PostgreSQL Database

Both targets use PostgreSQL as the storage backend (`STORE_BACKEND=postgres`).

### Connection

```bash
psql postgresql://taris:taris_openclaw_2026@localhost:5432/taris
```

### Schema Overview

| Table | Content |
|---|---|
| `users` | Registered users, roles, approval status |
| `chat_history` | LLM conversation history per user |
| `notes` | User notes (Markdown) |
| `calendar_events` | Calendar entries |
| `contacts` | Contact book |
| `documents` | RAG document metadata |
| `text_chunks` | RAG document chunks (FTS5 index) |
| `embeddings` | Vector embeddings for hybrid RAG |
| `security_events` | Access denials and audit log |

### Backup

```bash
pg_dump postgresql://taris:taris_openclaw_2026@localhost:5432/taris > taris_backup_$(date +%Y%m%d).sql
```

---

## 9. Testing

After every deployment, run regression tests:

```bash
# Quick unit tests (6s)
DEVICE_VARIANT=openclaw PYTHONPATH=src python3 -m pytest src/tests/telegram/ src/tests/screen_loader/ src/tests/llm/ -q

# Voice regression (T01–T96, ~162s)
DEVICE_VARIANT=openclaw PYTHONPATH=src python3 src/tests/test_voice_regression.py

# Web UI Playwright (~30s)
PYTHONPATH=src python3 -m pytest src/tests/ui/ -q

# Run all (sequential)
bash -c "DEVICE_VARIANT=openclaw PYTHONPATH=src python3 -m pytest src/tests/telegram/ src/tests/screen_loader/ src/tests/llm/ -q && DEVICE_VARIANT=openclaw PYTHONPATH=src python3 src/tests/test_voice_regression.py && PYTHONPATH=src python3 -m pytest src/tests/ui/ -q"
```

### PERF Baseline

After a clean restart, run a few Telegram commands and check PERF logs:

```bash
journalctl --user -u taris-telegram --since "5 min ago" | grep PERF
```

Expected: all PERF values < 2000 ms. Any value > 5000 ms = investigate immediately.

---

## 10. Admin Operations via Telegram

As an admin user, the following operations are available in the Telegram bot:

### User Management (Admin Panel → Users)
- **Pending Requests** — approve or block new users
- **User List** — view all registered users and roles
- **Add / Remove User** — manage access by Telegram chat ID

### LLM Switching (Admin Panel → AI / LLM)
- Switch between `openai`, `ollama`, `gemini`, `anthropic`, `taris`, `local` at runtime
- Set `LLM_PROVIDER` in `bot.env` and restart for permanent change

### System Monitoring (Admin Panel → System)
- **System Chat** — ask about system state in natural language (runs shell commands)
- **View Log** — last 50 lines of `telegram_bot.log`
- **Changelog** — full version history

### Voice Options (Admin Panel → Voice Opts)
See [howto_bot.md — Voice Settings](howto_bot.md) for the full list of toggles.

---

## 11. Troubleshooting

| Symptom | Check | Fix |
|---|---|---|
| Callbacks freeze (30–100s) | `free -m` — is swap full? | Set `FASTER_WHISPER_PRELOAD=0`; increase swap; kill memory-hungry processes |
| PERF > 5000 ms in logs | `free -m`; `ps aux --sort=-%mem` | See §4 Memory Management |
| `answer_callback_query failed: query is too old` | Normal if PERF > 60s | Root cause is the freeze — fix memory first |
| Ollama returns empty responses | `journalctl -u ollama` | Set `OLLAMA_THINK=false` for qwen3 models |
| Ollama model download fails | Network: IPv6 DNS issue | Apply `/etc/gai.conf` IPv4 preference fix (§7) |
| SintAItion TCP timeouts | EEE carrier drops | `ethtool --set-eee eth0 eee off` (§7) |
| Bot starts but stays at 500MB RSS | `FASTER_WHISPER_PRELOAD=1` still set | Add `FASTER_WHISPER_PRELOAD=0` to `bot.env` + restart |
| Web UI 502 Bad Gateway | Service stopped | `systemctl --user restart taris-web` |
| Database connection errors | PostgreSQL not running | `systemctl status postgresql` |
| STT cold-start delay (3–5s on first voice) | Expected on TariStation2 | Normal behavior with `FASTER_WHISPER_PRELOAD=0` |
| High CPU on first voice message | FasterWhisper loading | Expected; subsequent messages use cached model |

---

---

## 13. Remote Access from Internet

### Overview

| Target | Home (LAN) | Internet (Tailscale) |
|---|---|---|
| **SintAItion** | `ssh stas@192.168.178.175` or `ssh stas@SintAItion` | `ssh stas@100.112.120.3` |
| **TariStation2** | local machine (`cp`, `systemctl --user`) | — (home-only machine) |
| SSH password | `buerger` | `buerger` |

> **Tailscale** creates an encrypted point-to-point tunnel. No port forwarding or VPN configuration needed. Works from any network including mobile hotspot.

---

### SintAItion — Tailscale Setup (done 2026-04-03)

- **Tailscale IP:** `100.112.120.3`
- **Tailscale hostname:** `sintaition`
- **Account:** `stanislav.ulmer@`
- `tailscaled` service: enabled + auto-starts on boot

Verify connectivity:
```bash
ssh stas@100.112.120.3
# or
echo 'buerger' | sudo -S tailscale status
```

---

### One-Time Setup — Travel Laptop

Install Tailscale on your travel/development laptop:

```bash
# Linux / macOS
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
# → authorize in browser with stanislav.ulmer@ account
```

After authorization, verify:
```bash
ssh stas@100.112.120.3   # SintAItion reachable from anywhere
```

---

### Deploying to SintAItion from Internet

**Switch to Tailscale mode** (sets `OPENCLAW1_HOST=100.112.120.3`):

```bash
cd /path/to/sintaris-pl
source tools/use_tailscale.sh
```

Then deploy as normal (all `sshpass`/`scp` commands use `OPENCLAW1_HOST`):

```bash
# Example: deploy bot_config.py
sshpass -p "$OPENCLAW1PWD" scp -o StrictHostKeyChecking=no \
    src/core/bot_config.py stas@$OPENCLAW1_HOST:~/.taris/core/

# Restart services
sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no stas@$OPENCLAW1_HOST \
    "systemctl --user restart taris-telegram taris-web"
```

**Switch back to LAN mode** (when at home):

```bash
source tools/use_lan.sh
```

---

### `.env` Variables

| Variable | Value | Purpose |
|---|---|---|
| `OPENCLAW1_HOST` | `SintAItion` (home) or `100.112.120.3` (travel) | Used by all deploy commands |
| `OPENCLAW1_TAILSCALE_IP` | `100.112.120.3` | Permanent record of Tailscale IP |
| `OPENCLAW1_LAN_IP` | `192.168.178.175` | Permanent record of LAN IP |
| `OPENCLAW1PWD` | `buerger` | SSH password |

> **Never commit `.env`** — it contains credentials. It is gitignored.

---

### Troubleshooting Remote Access

| Symptom | Cause | Fix |
|---|---|---|
| `ssh: connect to host 100.112.120.3 port 22: No route to host` | Tailscale not running on laptop | `sudo tailscale up` on laptop |
| `ssh: connect to host 100.112.120.3 port 22: Connection refused` | `tailscaled` stopped on SintAItion | `ssh stas@192.168.178.175 "sudo systemctl restart tailscaled"` (from home) |
| `Permission denied (publickey,password)` | Wrong password | password is `buerger` |
| SSH hangs (no output) | Network issue / Tailscale relay | Wait 10s; retry; check `tailscale status` on both machines |
| `OPENCLAW1_HOST` not updated | `use_tailscale.sh` not sourced | Run `source tools/use_tailscale.sh` |

---

*See also: §7 Network Configuration for SintAItion LAN fixes (EEE, route metrics, IPv4 preference)*

---

## 12. Version Bump Procedure

After any user-visible change:

1. Update `BOT_VERSION` in `src/core/bot_config.py`
2. Prepend entry to `src/release_notes.json`
3. Validate: `python3 -c "import json,sys; json.load(sys.stdin)" < src/release_notes.json`
4. Commit and push
5. Deploy to TariStation2 → test → deploy to SintAItion

Use `/taris-bump-version` Copilot skill for automated version bumping.

---

*See also:*
- *[performance-report-2026-04-02.md](performance-report-2026-04-02.md) — root-cause analysis of the 2026-04-02 menu freeze*
- *[install-new-target.md](install-new-target.md) — full fresh installation guide*
- *[architecture/openclaw-integration.md](architecture/openclaw-integration.md) — OpenClaw architecture details*
