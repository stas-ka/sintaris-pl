# SSH Admin Access to SintAItion from Internet

## Overview

SintAItion sits behind a NAT router (home network, no public IP).  
Remote SSH admin access is provided via a **reverse SSH tunnel through the VPS** (dev2null.de).

```
Your machine ──── SSH ────> VPS (dev2null.de:22)
                               │
                    localhost:2222 (reverse tunnel)
                               │
                            SintAItion:22
```

**Tunnel**: SintAItion runs `autossh -R 2222:localhost:22 stas@dev2null.de`  
(part of `taris-tunnel.service`, added 2026-04-16)

---

## Method 1: SSH ProxyJump (Recommended — works from anywhere)

### One-time setup — add to `~/.ssh/config`

```
Host sintaition-remote
    HostName 127.0.0.1
    Port 2222
    User stas
    ProxyJump stas@dev2null.de
    StrictHostKeyChecking no
    IdentityFile ~/.ssh/id_ed25519
```

### Daily use

```bash
# Interactive shell
ssh sintaition-remote

# Run remote command
ssh sintaition-remote 'systemctl --user restart taris-web && systemctl --user status taris-web -n 5'

# Deploy a file
scp src/bot_web.py sintaition-remote:~/.taris/

# Deploy directory
scp -r src/web/templates/ sintaition-remote:~/.taris/web/

# Check logs
ssh sintaition-remote 'journalctl --user -u taris-web -n 30 --no-pager'
```

### From Windows (no ~/.ssh/config)

```powershell
# Shell
ssh -J stas@dev2null.de -p 2222 stas@127.0.0.1 -o StrictHostKeyChecking=no

# File copy
scp -J stas@dev2null.de -P 2222 -o StrictHostKeyChecking=no src\bot_web.py stas@127.0.0.1:~/.taris/

# Remote command
ssh -J stas@dev2null.de -p 2222 stas@127.0.0.1 -o StrictHostKeyChecking=no "systemctl --user restart taris-web"
```

---

## Method 2: Tailscale VPN (works if device is on same Tailscale network)

```bash
# SintAItion Tailscale IP: 100.112.120.3
ssh stas@100.112.120.3

# Install Tailscale on your machine, then join the 'stanislav.ulmer@' network
# → instant direct access, no VPS needed
```

Tailscale account: `stanislav.ulmer@`  
SintAItion node name: `sintaition`

---

## Method 3: LAN (home network only)

```bash
ssh stas@SintAItion.local    # mDNS — only works on same Wi-Fi
ssh stas@192.168.178.175     # Direct IP (may change via DHCP)
```

---

## Authorized SSH Keys

The following public keys are authorized on SintAItion (`~/.ssh/authorized_keys`):

| Key | Comment | Added |
|-----|---------|-------|
| ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGBSpZn4P... | worksafety-project@windows (dev machine) | 2026-04-16 |
| ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIIEoBtLA7... | stanislav.ulmer@gmail.com (VPS github key) | 2026-04-16 |

To add a new key: `echo 'ssh-ed25519 AAAA... comment' >> ~/.ssh/authorized_keys`

---

## Reverse Tunnel Service

**File**: `~/.config/systemd/user/taris-tunnel.service`

```ini
ExecStart=/usr/bin/autossh -M 0 \
  -o StrictHostKeyChecking=no \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -o BatchMode=yes \
  -i /home/stas/.ssh/vps_tunnel_key \
  -R 8086:localhost:8080 \     # SintAItion web UI → VPS:8086
  -R 8088:192.168.178.43:8080 \ # TariStation2 web → VPS:8088  
  -R 2222:localhost:22 \       # SSH admin tunnel → VPS:2222
  -N stas@dev2null.de
```

**Port 2222 is localhost-only on VPS** — not publicly exposed, ProxyJump through VPS required.

---

## Deployment from Internet (Replace LAN pscp/plink Commands)

Replace in any script or skill:
```bash
# Before (LAN only):
pscp -pw "$HOSTPWD" src\bot_web.py stas@SintAItion.local:~/.taris/
plink -pw "$HOSTPWD" stas@SintAItion.local "systemctl --user restart taris-web"

# After (works from internet):
scp -J stas@dev2null.de -P 2222 -o StrictHostKeyChecking=no src/bot_web.py stas@127.0.0.1:~/.taris/
ssh -J stas@dev2null.de -p 2222 stas@127.0.0.1 -o StrictHostKeyChecking=no "systemctl --user restart taris-web"
```
