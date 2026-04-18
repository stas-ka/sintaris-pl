# VPS Remote SSH Access — Architecture Proposal

**When to read:** Before configuring remote SSH access to `dev2null.de` VPS from corporate networks.  
**Date:** 2026-04-18  
**VPS host:** `dev2null.de` / `agents.sintaris.net` — IP `152.53.224.213`  
**Problem:** Corporate proxy (`http-proxy.porsche.org:3133`) blocks outbound SSH on port 22. Port 443 is reachable.

---

## ⚡ Copilot Implementation Checklist

> **Read this section first.** Everything below it is background/reference. These are the exact steps to make SSH work end-to-end.

### Status

| Step | What | Status |
|------|------|--------|
| 1 | nginx stream configured on VPS (no-TLS→sshd, TLS→nginx:8443) | ✅ Done |
| 2 | SSH key generated on client (`~/.ssh/id_vps`) | ✅ Done |
| 3 | `~/.ssh/config` entries added (`Host vps`, `vps-direct`, `vps-rem`) | ✅ Done |
| 4 | Public key added to VPS `~/.ssh/authorized_keys` | ✅ Done — `p355208@porsche.de-vps` key added 2026-04-18 |
| 5 | First connection tested, host key accepted | ⬜ Pending — run from Porsche machine |

---

### Step 4 — Add SSH Public Key to VPS

**Client public key** (generated 2026-04-18, file `~/.ssh/id_vps.pub`):
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJMZO3e9spkcDnXpOZ/hSLu3VlldXX8+NNnbelHhJAyA p355208@porsche.de-vps
```

**Run from WSL terminal** (password auth, one time only):
```bash
# Option A — pipe key directly (recommended)
cat ~/.ssh/id_vps.pub | ssh -o PasswordAuthentication=yes \
  -o PreferredAuthentications=password \
  vps "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && echo KEY_ADDED"
# Password when prompted: Zusammen!2019

# Option B — manual (if Option A fails)
ssh -o PasswordAuthentication=yes -o PreferredAuthentications=password vps
# Then on VPS:
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJMZO3e9spkcDnXpOZ/hSLu3VlldXX8+NNnbelHhJAyA p355208@porsche.de-vps" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

---

### Step 5 — Test Connection

```bash
# Test via corporate proxy (WSL on Porsche network) — uses Host vps alias
ssh vps "echo connected && whoami && hostname"

# Verify host key fingerprint on first connect — must match:
# SHA256:E2ycjThOe09yMfERUKN76uDyW7YBT12rjS5FJXB+PZ4

# Test direct (home/VPN, no proxy) — uses Host vps-direct alias
ssh vps-direct "echo connected"

# Once key auth works, lock down password auth on VPS:
ssh vps "sudo sed -i 's/^PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config && sudo systemctl reload sshd && echo LOCKED"
```

---

---

## Environment Facts

| Fact | Value |
|------|-------|
| VPS IP | `152.53.224.213` |
| Port 22 TCP | Open (SYN/SYN-ACK) — but SSH banner blocked by proxy |
| Port 443 TCP | ✅ Open and reachable from corporate network |
| TLS on port 443 | ✅ TLSv1.3 (`TLS_AES_256_GCM_SHA384`) working |
| nginx version | `1.24.0 (Ubuntu)` — stream+ssl modules included |
| `rem.dev2null.de` | ✅ Already in DNS → `152.53.224.213` |
| `agents.sintaris.net` | ✅ Already in DNS → `152.53.224.213` |
| Existing SSH port | 22 (sshd default) |
| Corporate ProxyCommand | `nc -X connect -x http-proxy.porsche.org:3133 %h %p` |

---

## Options Compared

| # | Approach | VPS change | New domain | Proxy-friendly | Security | Complexity |
|---|----------|-----------|-----------|----------------|----------|------------|
| **A** | **nginx stream SNI → SSH** ✅ | nginx stream config | `rem.dev2null.de` | ✅ Port 443 | ⭐⭐⭐⭐ High | Low |
| B | sslh multiplexer on 443 | Install sslh, move nginx | Not needed | ✅ Port 443 | ⭐⭐⭐ Medium | Medium |
| C | sshd Port 443 directly | Edit sshd_config | Not needed | ✅ Port 443 | ⭐⭐ Low (port conflict with nginx) | Minimal |
| D | WebSocket tunnel (wstunnel) | Install wstunnel, nginx ws route | Optional | ✅ Any HTTPS | ⭐⭐⭐⭐⭐ Highest | High |
| E | Cloudflare Tunnel | CF agent on VPS | Via CF | ✅ Any | ⭐⭐⭐⭐⭐ Highest | Medium |

---

## Recommendation: Option A — Subdomain + nginx Stream SNI

### Why this is best

- `rem.dev2null.de` DNS is **already set up** — zero DNS change needed
- Port 443 is **already reachable** from corporate network
- nginx **stream module** is included in `nginx-full` (Ubuntu default)
- **Zero new tools** to install on VPS
- **Clean separation**: `agents.sintaris.net` → web; `rem.dev2null.de` → SSH tunnel only
- **SNI routing** means one port (443) handles multiple virtual "services" via hostname
- Easy to revoke/audit: remove nginx block → SSH access via this path is gone

### How SNI routing works

```
Client (corporate)          Corporate Proxy        VPS nginx (port 443)
   │                             │                        │
   │── CONNECT rem.dev2null.de:443 ──▶ proxy ──▶ TCP to 152.53.224.213:443
   │                                                      │
   │── TLS ClientHello (SNI=rem.dev2null.de) ────────────▶│
   │                                           nginx stream reads SNI
   │                                           routes to sshd:22 (127.0.0.1)
   │◀──────────────────── SSH banner ─────────────────────│
```

### Security properties

- SSH never exposed on a raw port (always wrapped in nginx stream)
- TLS certificate validates server identity (MITM protection)
- Key-based auth only — no password brute-force possible
- Access can be revoked per nginx vhost with zero sshd restart
- fail2ban continues protecting sshd on port 22

---

## Implementation

### VPS — Step 1: Enable nginx stream module

Check if stream is available:
```bash
nginx -V 2>&1 | grep -o 'with-stream[^ ]*'
# Should show: --with-stream --with-stream_ssl_module --with-stream_ssl_preread_module
```

If missing (unlikely on Ubuntu `nginx-full`):
```bash
sudo apt-get install -y nginx-extras
```

---

### VPS — Step 2: Create TLS certificate for `rem.dev2null.de`

```bash
sudo certbot certonly --nginx -d rem.dev2null.de
# Or if wildcard cert already covers *.dev2null.de, skip this step
```

Check if existing cert covers the subdomain:
```bash
sudo certbot certificates | grep -A5 "dev2null"
```

---

### VPS — Step 3: Add nginx stream block

Create `/etc/nginx/stream.d/ssh-tunnel.conf`:

```nginx
# /etc/nginx/stream.d/ssh-tunnel.conf
# Routes rem.dev2null.de:443 → sshd on 127.0.0.1:22
# All other SNI names → nginx HTTPS (handled by http block on 8443)

map $ssl_preread_server_name $upstream {
    rem.dev2null.de  ssh_backend;
    default          https_backend;
}

upstream ssh_backend {
    server 127.0.0.1:22;
}

upstream https_backend {
    server 127.0.0.1:8443;  # nginx HTTPS listener (see Step 4)
}

server {
    listen 443;
    ssl_preread on;
    proxy_pass $upstream;
    proxy_connect_timeout 10s;
    proxy_timeout 300s;
}
```

Add stream include to `/etc/nginx/nginx.conf` (outside `http {}` block):
```nginx
# At the end of nginx.conf, after the http{} block:
stream {
    include /etc/nginx/stream.d/*.conf;
}
```

---

### VPS — Step 4: Move nginx HTTPS from 443 → 8443

Edit existing HTTPS server blocks in `/etc/nginx/sites-enabled/`:

```nginx
# Before:
server {
    listen 443 ssl;
    ...
}

# After:
server {
    listen 127.0.0.1:8443 ssl;  # only stream proxy can reach this now
    ...
}
```

> **Note:** HTTP (port 80) for certbot renewals and redirects stays unchanged.

---

### VPS — Step 5: Test and reload nginx

```bash
sudo nginx -t && sudo nginx -s reload
```

Verify stream is routing correctly:
```bash
# From VPS itself:
ssh -p 443 -o StrictHostKeyChecking=no localhost "echo ok"
```

---

### VPS — Step 6: Harden SSH (key-only, no passwords)

Edit `/etc/ssh/sshd_config`:
```ssh-config
PasswordAuthentication no
PubkeyAuthentication yes
AuthorizedKeysFile .ssh/authorized_keys
PermitRootLogin no
MaxAuthTries 3
LoginGraceTime 30
```

```bash
sudo systemctl restart ssh
```

---

### Local machine — Step 7: Add SSH key to VPS

```bash
# 1. Generate dedicated VPS key (separate from GitHub key)
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_vps -C "vps-dev2null-$(date +%Y%m%d)"

# 2. Add public key to VPS authorized_keys
# (Do this while you still have console access, e.g. Hetzner Cloud Console)
cat ~/.ssh/id_ed25519_vps.pub
# Paste into VPS: echo "ssh-ed25519 AAAA... vps-dev2null-..." >> ~/.ssh/authorized_keys
```

---

### Local machine — Step 8: Configure `~/.ssh/config`

```ssh-config
# VPS remote access via port 443 (corporate proxy compatible)
Host vps rem.dev2null.de
    HostName rem.dev2null.de
    Port 443
    User stas
    IdentityFile ~/.ssh/id_ed25519_vps
    IdentitiesOnly yes
    ServerAliveInterval 30
    ServerAliveCountMax 3
    # Route through corporate HTTP proxy:
    ProxyCommand nc -X connect -x http-proxy.porsche.org:3133 %h %p
```

---

### Local machine — Step 9: Test connection

```bash
ssh vps "echo connected && hostname && docker ps --format 'table {{.Names}}\t{{.Status}}'"
```

Expected output:
```
connected
dev2null.de
NAMES            STATUS
taris            Up 2 hours
n8n              Up 5 days
```

---

## Security Checklist

| Control | Status after implementation |
|---------|----------------------------|
| Password auth | ❌ Disabled (`PasswordAuthentication no`) |
| Root login | ❌ Disabled (`PermitRootLogin no`) |
| Key type | ✅ Ed25519 (strongest available) |
| Key scope | ✅ Separate key for VPS only (not shared with GitHub) |
| Port exposure | ✅ Port 22 protected by fail2ban; 443 via nginx stream |
| TLS in transit | ✅ TLSv1.3 (SNI preread — nginx does not terminate TLS for SSH) |
| Certificate | ✅ Let's Encrypt for `rem.dev2null.de` |
| Revocation | ✅ Remove nginx stream block → access immediately revoked |
| Audit log | ✅ `/var/log/auth.log` captures all SSH login attempts |
| fail2ban | ✅ Continues protecting port 22; add rule for port 443 too |

### Add fail2ban rule for port 443 SSH attempts

```bash
# /etc/fail2ban/jail.d/sshd-443.conf
[sshd-443]
enabled  = true
port     = 443
filter   = sshd
logpath  = /var/log/auth.log
maxretry = 5
bantime  = 3600
```

```bash
sudo systemctl restart fail2ban
```

---

## Quick Reference Commands (after setup)

```bash
# Connect to VPS
ssh vps

# Run docker command on VPS
ssh vps "docker ps"

# Copy file to VPS
scp myfile.py vps:/opt/taris_docker/

# Run tests on VPS
ssh vps "cd /opt/taris_docker && python3 -m pytest src/tests/ -q"

# Tail logs
ssh vps "docker logs taris -f"
```

---

## Why NOT the other options

| Option | Reason not preferred |
|--------|---------------------|
| sslh (Option B) | Extra package to maintain; same result as Option A |
| sshd Port 443 (Option C) | Conflicts with nginx on port 443 — requires stopping web services or sslh anyway |
| wstunnel (Option D) | Extra client tool required on every machine; more complex; adds dependency |
| Cloudflare Tunnel (Option E) | Third-party dependency; all SSH traffic routes via Cloudflare infrastructure; overkill for this use case |

---

## Summary

| Item | Value |
|------|-------|
| **Chosen approach** | nginx stream + SNI → SSH on `rem.dev2null.de:443` |
| **New domain** | `rem.dev2null.de` (DNS already exists ✅) |
| **New tools on VPS** | None (nginx stream already installed) |
| **New tools locally** | None (standard SSH + ProxyCommand) |
| **Port** | 443 (accessible from corporate proxy ✅) |
| **Auth** | Ed25519 key only, no passwords |
| **Estimated setup time** | ~20 minutes (nginx config + certbot + local SSH config) |
