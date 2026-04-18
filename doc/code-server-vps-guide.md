# Code-Server VPS Guide — Browser-Based VS Code at `vsc.dev2null.de`

**When to read:** When setting up, accessing, or maintaining the browser-based VS Code environment on the VPS.  
**Last updated:** 2026-04-18

---

## Overview

Code-server provides a full VS Code IDE accessible from **any browser** — no SSH client, no local VS Code installation required. This is the primary development interface for the VPS from restricted corporate networks.

| Property | Value |
|---|---|
| URL | `https://vsc.dev2null.de` |
| Auth | Password-based (config.yaml) |
| VPS host | `dev2null.de` (152.53.224.213) |
| Port | 443 (HTTPS via nginx) |
| Code-server version | v4.116.0 |
| VS Code version | 1.116.0 |
| Service | `code-server.service` (systemd, user `stas`) |
| Copilot Chat | v0.44.0 — **patched and working** ✅ |

---

## 1 — Accessing Code-Server

**Open in any browser:** `https://vsc.dev2null.de`

Enter the password when prompted. No SSH, no VPN, no client installation needed.

> **Password:** stored in `/home/stas/.config/code-server/config.yaml` on VPS (see §4 for admin access).  
> **Corporate networks:** Port 443 HTTPS is always allowed through corporate proxies. Code-server works directly without any proxy configuration.

After login, open a workspace folder (e.g. `/home/stas/projects/sintaris-pl`) to activate all extensions including GitHub Copilot.

---

## 2 — GitHub Copilot Setup (Patched)

Copilot requires **two patches** to work in code-server, both already applied on the VPS.

### Why it needs patching

Code-server bundles its own `github-authentication` extension which hardcodes the wrong OAuth client ID (`01ab8ac9400c4e429b23` — code-server's app). GitHub Copilot API only trusts VS Code's OAuth app (`Iv1.b507a08c87ecfe98`). Additionally, code-server's `context.secrets` API proxies to browser localStorage, not to server-side keyring — so standard server-side session injection does not work.

### Patch 1 — OAuth Client ID (applied once)

**File:** `/usr/lib/code-server/lib/vscode/extensions/github-authentication/dist/extension.js`  
**Change:** `Gt={gitHubClientId:"01ab8ac9400c4e429b23"}` → `"Iv1.b507a08c87ecfe98"`

### Patch 2 — File-based Session Fallback (applied once)

**File:** same `extension.js`  
**Change:** `getToken()` patched to read `/home/stas/.copilot-token.json` before falling back to browser localStorage secrets.

### Token file

**Path:** `/home/stas/.copilot-token.json` (chmod 600, owned by `stas`)

Contains 3 GitHub OAuth sessions decrypted from local VS Code (account `stas-ka`, ID `9452205`).  
The critical session has scopes `read:user, user:email, repo, workflow` — required by Copilot Chat.

**Verified:** All tokens call `https://api.github.com/copilot_internal/v2/token` → HTTP 200 ✅

### After code-server updates

If code-server is upgraded, `extension.js` is overwritten. Re-apply both patches:

```bash
# 1. Verify current client ID
grep -o 'gitHubClientId:"[^"]*"' /usr/lib/code-server/lib/vscode/extensions/github-authentication/dist/extension.js

# 2. Re-apply client ID patch
sudo sed -i 's/gitHubClientId:"01ab8ac9400c4e429b23"/gitHubClientId:"Iv1.b507a08c87ecfe98"/g' \
  /usr/lib/code-server/lib/vscode/extensions/github-authentication/dist/extension.js

# 3. Verify token file still exists (tokens are long-lived — usually valid for months)
ls -la /home/stas/.copilot-token.json
node -e "const s=JSON.parse(require('fs').readFileSync('/home/stas/.copilot-token.json')); console.log('Sessions:', s.length)"

# 4. Restart code-server
sudo systemctl restart code-server
```

### Refreshing expired tokens

The `gho_...` tokens are long-lived but can expire or be revoked. If Copilot stops working, refresh by re-extracting from local VS Code:

**Windows (PowerShell):**
```powershell
# AES key (DPAPI-extracted, stable as long as Windows user profile exists):
$AES_KEY = "ad34742b55adcc246f0f07efd8e307d8c2c4a4990eb0309717d939822f84f502"

# Re-run the extraction pipeline (scripts in C:\tmp\):
python C:\tmp\get_session.py   # reads state.vscdb → decrypts → writes C:\tmp\vscode_sessions.json

# Upload to VPS:
pscp -pw "$VPS_PWD" C:\tmp\vscode_sessions.json "stas@dev2null.de:/home/stas/.copilot-token.json"
plink -pw "$VPS_PWD" -batch stas@dev2null.de "chmod 600 /home/stas/.copilot-token.json && sudo systemctl restart code-server"
```

---

## 3 — Deployment / Install

### Prerequisites

- Debian/Ubuntu VPS with nginx, certbot, systemd
- DNS: `vsc.dev2null.de → <VPS_IP>` (A record)
- TLS: Let's Encrypt cert for `vsc.dev2null.de`

### Step 1 — Install code-server

```bash
# ARM64 (aarch64)
curl -fsSL https://code-server.dev/install.sh | sh
# or for a specific version:
VERSION=4.116.0
curl -fOL "https://github.com/coder/code-server/releases/download/v${VERSION}/code-server_${VERSION}_arm64.deb"
sudo dpkg -i code-server_${VERSION}_arm64.deb
```

### Step 2 — Configure

Edit `/home/stas/.config/code-server/config.yaml`:

```yaml
bind-addr: 127.0.0.1:8088
auth: password
password: <PASSWORD>        # set from .env VPS_CODE_SERVER_PWD
cert: false                 # TLS handled by nginx
```

### Step 3 — Systemd service

```bash
# Copy service file from repo
sudo cp deploy/system-configs/vps/code-server.service /etc/systemd/system/code-server.service
sudo systemctl daemon-reload
sudo systemctl enable code-server
sudo systemctl start code-server
```

Service file (`deploy/system-configs/vps/code-server.service`):
```ini
[Unit]
Description=code-server (browser VS Code)
After=network.target

[Service]
Type=simple
User=stas
Environment=HOME=/home/stas
EnvironmentFile=-/home/stas/.code-server-env
ExecStart=/usr/local/bin/code-server --config /home/stas/.config/code-server/config.yaml /home/stas
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Step 4 — nginx reverse proxy

```bash
# Install TLS cert
sudo certbot --nginx -d vsc.dev2null.de

# Copy nginx vhost from repo
sudo cp deploy/system-configs/vps/nginx/vsc.dev2null.de.conf /etc/nginx/sites-available/vsc.dev2null.de
sudo ln -s /etc/nginx/sites-available/vsc.dev2null.de /etc/nginx/sites-enabled/
sudo nginx -t && sudo nginx -s reload
```

Nginx vhost (`deploy/system-configs/vps/nginx/vsc.dev2null.de.conf`):
```nginx
server {
    listen 127.0.0.1:8443 ssl;
    server_name vsc.dev2null.de;

    ssl_certificate     /etc/letsencrypt/live/vsc.dev2null.de/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/vsc.dev2null.de/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;

    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection upgrade;
    proxy_set_header Host $host;
    proxy_read_timeout 86400;

    location / {
        proxy_pass http://127.0.0.1:8088/;
    }
}
```

### Step 5 — Apply Copilot patches

See §2 above. Run client ID patch + upload token file.

### Step 6 — Verify

```bash
sudo systemctl status code-server
curl -sk https://vsc.dev2null.de | grep -o 'code-server[^"]*'
```

---

## 4 — Administration

### Service management (on VPS via SSH admin)

```bash
# Status
sudo systemctl status code-server

# Restart (needed after Copilot patch or config change)
sudo systemctl restart code-server

# Tail logs
journalctl -u code-server -f --no-pager

# Check code-server version
code-server --version
```

### Extension host logs

Extensions only load when a browser connects and opens a workspace:

```bash
# List sessions (each browser connection creates a new dir)
ls ~/.local/share/code-server/logs/

# GitHub auth extension log (look for Copilot-Patch message)
find ~/.local/share/code-server/logs -path "*github-authentication*" -name "*.log" | sort | tail -1 | xargs tail -30

# Copilot Chat log
find ~/.local/share/code-server/logs -path "*copilot-chat*" -name "*.log" | sort | tail -1 | xargs tail -30
```

**Success indicators in GitHub auth log:**
```
[info] [Copilot-Patch] Using file token
[info] Got 3 stored sessions
```

**Success indicators in Copilot Chat log:**
```
[info] Logged in as stas-ka
```

### Change password

```bash
# Edit config on VPS
nano /home/stas/.config/code-server/config.yaml
# Change the 'password:' line
sudo systemctl restart code-server
```

### Update code-server

```bash
VERSION=4.117.0  # new version
curl -fOL "https://github.com/coder/code-server/releases/download/v${VERSION}/code-server_${VERSION}_arm64.deb"
sudo dpkg -i code-server_${VERSION}_arm64.deb
# Re-apply Copilot patches (see §2)!
sudo systemctl restart code-server
```

---

## 5 — Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| 502 Bad Gateway at `vsc.dev2null.de` | code-server not running | `sudo systemctl restart code-server` |
| Sign-in button does nothing | Extension JS blocked by browser | Hard-refresh (Ctrl+Shift+R); check extension logs |
| Copilot says "Not authorized" | Token file missing or expired | Re-upload `/home/stas/.copilot-token.json` (see §2) |
| Copilot returns 404 | Client ID patch lost (after upgrade) | Re-apply Patch 1 (see §2) |
| Extension host doesn't start | No workspace opened | Open a folder in the Explorer panel |
| `Personal Access Tokens are not supported` | PAT used instead of OAuth token | PATs never work with Copilot API — use OAuth sessions only |
| Slow response / timeout | Large files, VPS CPU load | Check `htop` on VPS; consider opening specific subfolder |

### Quick diagnostic from Windows

```powershell
$envContent = Get-Content D:\Projects\workspace\sintaris-openclaw\.env -Encoding UTF8
$VPS_PWD = ($envContent | Select-String "^VPS_PWD=").ToString().Split("=",2)[1].Trim()
$hostkey = "SHA256:E2ycjThOe09yMfERUKN76uDyW7YBT12rjS5FJXB+PZ4"

# Check service and latest logs
plink -pw "$VPS_PWD" -hostkey "$hostkey" -batch stas@dev2null.de @"
echo '=== Service ==='
systemctl status code-server --no-pager | head -8
echo '=== Token file ==='
ls -la /home/stas/.copilot-token.json
echo '=== Client ID patch ==='
grep -o 'gitHubClientId:\"[^\"]*\"' /usr/lib/code-server/lib/vscode/extensions/github-authentication/dist/extension.js | head -1
"@
```

Expected:
```
Active: active (running)
-rw------- 1 stas stas ... .copilot-token.json
gitHubClientId:"Iv1.b507a08c87ecfe98"
```

---

## 6 — Architecture Notes

```
Browser (any device, any network)
    │ HTTPS port 443
    ▼
nginx (vsc.dev2null.de)
    │ HTTP port 8088 (loopback)
    ▼
code-server (VS Code 1.116.0)
    │
    ├── Extension host (Node.js)
    │     ├── vscode.github-authentication ← Patched: reads /home/stas/.copilot-token.json
    │     └── GitHub.copilot-chat ← Uses sessions from above
    │
    └── /home/stas/projects/sintaris-pl  ← workspace
```

**Why browser-based is the right choice:**
- Works from any machine — corporate laptop, home PC, tablet
- No local installation required
- Corporate proxies allow HTTPS (port 443) — code-server works without any client-side configuration
- All compute and extensions run on the VPS — consistent environment regardless of client device

---

## 7 — File Inventory

| File | Purpose |
|---|---|
| `deploy/system-configs/vps/code-server.service` | systemd service unit |
| `deploy/system-configs/vps/nginx/vsc.dev2null.de.conf` | nginx reverse proxy vhost |
| `/home/stas/.config/code-server/config.yaml` | code-server config (VPS only, not in git) |
| `/home/stas/.copilot-token.json` | OAuth sessions for Copilot (VPS only, not in git) |
| `/usr/lib/code-server/lib/vscode/extensions/github-authentication/dist/extension.js` | Patched extension (VPS) |
| `/usr/lib/code-server/lib/vscode/extensions/github-authentication/dist/extension.js.bak` | Original backup (before any patch) |
| `/usr/lib/code-server/lib/vscode/extensions/github-authentication/dist/extension.js.bak2` | Backup after client ID patch only |
| `/usr/lib/code-server/lib/vscode/product.json` | Patched with gitHubAuthentication clientId (informational) |

---

*Related: `doc/architecture/deployment.md` §VPS, `deploy/system-configs/vps/`*
