# SSH Access to VPS via Port 443 — Client Setup Guide

**Target**: `dev2null.de` (VPS, 152.53.224.213)  
**Port**: 443 (nginx stream routes SSH → sshd:22 transparently)  
**Host key fingerprint**: `SHA256:E2ycjThOe09yMfERUKN76uDyW7YBT12rjS5FJXB+PZ4`  
**Use case**: Corporate/restricted networks that block port 22 but allow outbound HTTPS (port 443)

---

## 0 — WSL Quick Start (Porsche network — already configured)

> **Your `~/.ssh/config` is already set up** with `Host vps` (via corporate proxy) and `Host vps-direct` (no proxy).  
> Your key `~/.ssh/id_vps` is generated and added to the VPS.  
> **Just open WSL and run the commands below.**

### 0.1 — First connection (one time only)

```bash
# Verify connection — accept host key fingerprint when prompted
ssh vps "echo connected && whoami && hostname"
# Expected: connected / stas / dev2null.de
# Fingerprint to accept: SHA256:E2ycjThOe09yMfERUKN76uDyW7YBT12rjS5FJXB+PZ4
```

### 0.2 — Interactive shell on VPS

```bash
# Open interactive shell
ssh vps

# Then you're logged in as stas@dev2null.de — type any Linux commands:
ls /opt/taris-docker/
docker ps
```

### 0.3 — Run single commands remotely

```bash
# Check which processes are running
ssh vps "docker ps"

# Check running taris bot token
ssh vps "grep BOT_TOKEN /opt/taris-docker/bot.env"

# Check taris bot version on VPS
ssh vps "docker exec taris-vps-telegram grep BOT_VERSION /app/core/bot_config.py"

# View live bot logs (last 50 lines)
ssh vps "docker logs taris-vps-telegram --tail 50"

# Follow logs in real time (Ctrl+C to stop)
ssh vps "docker logs -f taris-vps-telegram"

# Check web UI logs
ssh vps "docker logs taris-vps-web --tail 30"
```

### 0.4 — Run tests inside Docker on VPS

```bash
# Full voice regression suite inside telegram container
ssh vps "docker exec taris-vps-telegram python3 /app/tests/test_voice_regression.py"

# Quick unit tests
ssh vps "docker exec taris-vps-telegram python3 -m pytest /app/tests/telegram/ -q"

# Web UI sanity check
ssh vps "docker exec taris-vps-web python3 -c 'import bot_web; print(\"web ok\")'"
```

### 0.5 — Deploy updated source to VPS

```bash
# Sync changed Python files from WSL project to VPS Docker app dir
rsync -av --progress \
  ~/projects/sintaris-pl/src/ \
  stas@dev2null.de:/opt/taris-docker/app/src/ \
  -e "ssh -p 443 -i ~/.ssh/id_vps -o ProxyCommand='nc -X connect -x http-proxy.porsche.org:3133 %h %p'"

# After rsync — restart containers to pick up changes (volume-mounted, no rebuild)
ssh vps "cd /opt/taris-docker && docker compose restart taris-telegram taris-web"

# Verify new version running
ssh vps "docker logs taris-vps-telegram --tail 10"
```

### 0.6 — File operations

```bash
# Download a file from VPS
scp -P 443 stas@dev2null.de:/opt/taris-docker/bot.env ~/vps-bot.env

# Upload a file to VPS
scp -P 443 src/core/bot_config.py stas@dev2null.de:/opt/taris-docker/app/src/core/

# Note: scp uses the Host vps alias automatically if configured in ~/.ssh/config
scp vps:/opt/taris-docker/bot.env ~/vps-bot.env
```

### 0.7 — VPS system management

```bash
# Check disk usage
ssh vps "df -h"

# Check Docker container status and resource usage
ssh vps "docker stats --no-stream"

# Restart a single container
ssh vps "docker restart taris-vps-telegram"

# Stop all taris containers
ssh vps "cd /opt/taris-docker && docker compose down"

# Start all taris containers
ssh vps "cd /opt/taris-docker && docker compose up -d"

# Check PostgreSQL on VPS
ssh vps "docker ps | grep postgres"
```

### 0.8 — If not on Porsche network (home/VPN)

```bash
# Use vps-direct alias (no corporate proxy needed)
ssh vps-direct "echo connected"

# All other commands work the same — just replace 'vps' with 'vps-direct':
ssh vps-direct "docker ps"
ssh vps-direct "docker logs taris-vps-telegram --tail 30"
```

---

## 1 — Find the Corporate Proxy Address

Before configuring SSH, identify the proxy your restricted machine uses:

**Windows (PowerShell):**
```powershell
# Option A — Internet Explorer / system proxy
(Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings").ProxyServer

# Option B — WinHTTP proxy
netsh winhttp show proxy

# Option C — environment variable
$env:HTTPS_PROXY; $env:http_proxy
```

**Linux / macOS:**
```bash
echo $http_proxy $https_proxy
# or check PAC/WPAD config in browser settings
```

You'll get something like `proxy.corp.example.com:3133` or `http://10.x.x.x:8080`. Note the host and port — you'll need them below.

---

## 2 — Option A: OpenSSH (Linux, macOS, WSL, Windows OpenSSH)

### 2.1 — Install a CONNECT helper

The `ProxyCommand` needs a CONNECT-capable helper (`nc`, `corkscrew`, or `connect-proxy`):

**Linux:**
```bash
sudo apt-get install netcat-openbsd   # ubuntu/debian (nc with -X support)
# or:
sudo apt-get install connect-proxy
```

**macOS:**
```bash
brew install netcat   # or it may already be installed
```

**Windows (using WSL):** Install inside WSL same as Linux above.

**Windows (native OpenSSH):** Use `connect.exe` — download from:
- https://github.com/gotoh/ssh-connect/releases (connect.exe)
- Place it somewhere on your PATH (e.g. `C:\Windows\System32\`)

### 2.2 — Configure `~/.ssh/config`

Add the following block to `~/.ssh/config` (create the file if it doesn't exist):

```ssh-config
Host vps
    HostName dev2null.de
    User stas
    Port 443
    # Replace <PROXY_HOST> and <PROXY_PORT> with your corporate proxy
    ProxyCommand nc -X connect -x <PROXY_HOST>:<PROXY_PORT> %h %p
    # Alternative if nc doesn't support -X (e.g. on Windows):
    # ProxyCommand connect -H <PROXY_HOST>:<PROXY_PORT> %h %p
    ServerAliveInterval 30
    ServerAliveCountMax 3
```

**Example with known proxy `proxy.example.com:3133`:**
```ssh-config
Host vps
    HostName dev2null.de
    User stas
    Port 443
    ProxyCommand nc -X connect -x proxy.example.com:3133 %h %p
    ServerAliveInterval 30
    ServerAliveCountMax 3
```

### 2.3 — Generate SSH key (first time only)

```bash
ssh-keygen -t ed25519 -C "mycomputer@corp" -f ~/.ssh/id_vps
```

Share the contents of `~/.ssh/id_vps.pub` with the VPS admin to add to `~/.ssh/authorized_keys`.

### 2.4 — If using a specific key file

Add to the `Host vps` block:
```
    IdentityFile ~/.ssh/id_vps
```

### 2.5 — Test the connection

```bash
ssh vps "echo connected"
# → connected
```

If prompted to verify host key, check it matches:
```
SHA256:E2ycjThOe09yMfERUKN76uDyW7YBT12rjS5FJXB+PZ4
```

---

## 3 — Option B: PuTTY / plink (Windows, no WSL)

### 3.1 — Download PuTTY suite

Download PuTTY from https://www.putty.org and install. You'll need:
- `putty.exe` — GUI SSH client
- `plink.exe` — command-line SSH client
- `puttygen.exe` — key generator

### 3.2 — Generate SSH key

1. Open **PuTTYgen** → Key type: **ED25519** → click **Generate**
2. Move mouse to generate randomness
3. Click **Save private key** → save as `id_vps.ppk`
4. Copy the text from the "Public key for pasting into OpenSSH…" box
5. Share this public key with the VPS admin

### 3.3 — Configure PuTTY session

1. Open PuTTY
2. **Session:**
   - Host Name: `dev2null.de`
   - Port: `443`
   - Connection type: **SSH**
3. **Connection → Proxy:**
   - Proxy type: **HTTP**
   - Proxy hostname: `<PROXY_HOST>` (e.g. `proxy.example.com`)
   - Port: `<PROXY_PORT>` (e.g. `3133`)
4. **Connection → SSH → Auth → Credentials:**
   - Private key file: browse to `id_vps.ppk`
5. **Connection → SSH → Host keys:**
   - In "Manually-specified host keys" paste:
     `ssh-ed25519 SHA256:E2ycjThOe09yMfERUKN76uDyW7YBT12rjS5FJXB+PZ4`
6. **Session:** Type a name (e.g. `vps-443`) in "Saved Sessions" → **Save**
7. Click **Open** to connect

### 3.4 — plink command line

```powershell
# Password auth (temporary test)
plink -pw "PASSWORD" -P 443 `
    -proxycmd "connect.exe -H proxy.example.com:3133 %host %port" `
    stas@dev2null.de "echo connected"

# Key auth
plink -i id_vps.ppk -P 443 `
    -proxycmd "connect.exe -H proxy.example.com:3133 %host %port" `
    stas@dev2null.de "echo connected"

# With known hostkey (batch/non-interactive)
plink -pw "PASSWORD" -hostkey "SHA256:E2ycjThOe09yMfERUKN76uDyW7YBT12rjS5FJXB+PZ4" `
    -P 443 stas@dev2null.de "echo connected"
```

---

## 4 — Option C: Windows OpenSSH + `connect.exe` (no WSL needed)

### 4.1 — Enable Windows OpenSSH client

```powershell
# Run as Administrator
Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0
```

### 4.2 — Download `connect.exe`

Download from: https://github.com/gotoh/ssh-connect/releases  
Place `connect.exe` in `C:\Windows\System32\` (or add its folder to PATH).

### 4.3 — Configure SSH

Create or edit `C:\Users\<USERNAME>\.ssh\config`:

```ssh-config
Host vps
    HostName dev2null.de
    User stas
    Port 443
    ProxyCommand connect.exe -H <PROXY_HOST>:<PROXY_PORT> %h %p
    ServerAliveInterval 30
```

### 4.4 — Test

```powershell
ssh vps "echo connected"
```

---

## 5 — Option D: No proxy available — direct port 443

If the network blocks port 22 but allows direct outbound port 443 (no proxy required):

```bash
# Direct connection without proxy
ssh -p 443 stas@dev2null.de "echo connected"
```

Or in `~/.ssh/config`:
```ssh-config
Host vps
    HostName dev2null.de
    User stas
    Port 443
    ServerAliveInterval 30
```

---

## 6 — Add Your SSH Public Key to VPS

After generating a key pair, send the **public key** (`.pub` file content) to the VPS admin.

Format: `ssh-ed25519 AAAA... yourname@machine`

The admin appends it to `/home/stas/.ssh/authorized_keys` on the VPS.

Once added, password auth is no longer needed — key auth is automatic.

---

## 7 — Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Connection refused` on port 443 | nginx not running on VPS | Check VPS `sudo systemctl status nginx` |
| `ssh_exchange_identification: Connection closed` | Proxy blocking or CONNECT not allowed | Try direct (Option D), or ask IT for CONNECT allow-list |
| `Permission denied (publickey,password)` | Key not added to VPS yet | Share public key with VPS admin |
| `Proxy CONNECT failed (code 403)` | Proxy blocks CONNECT to port 443 | Some proxies only allow CONNECT to known HTTPS hosts |
| `Host key verification failed` | Wrong/cached host key | Remove old entry: `ssh-keygen -R "[dev2null.de]:443"` |
| `Timeout` | Port 443 filtered upstream | Try from different network |
| PuTTY: `Connection abandoned` in batch mode | Host key not cached | Add hostkey via `-hostkey` flag or accept interactively first |

### Verbose debug output

```bash
ssh -vvv -p 443 stas@dev2null.de 2>&1 | head -50
```

Look for:
- `Connecting to proxy...` → proxy is being used
- `channel 0: open confirm` → tunnel established
- `Authenticated` → login OK

---

## 8 — VPS Technical Details (for reference)

| Item | Value |
|---|---|
| VPS hostname | `dev2null.de` (also `mail.dev2null.de`) |
| VPS IP | `152.53.224.213` |
| SSH port | `22` (internal) / `443` (external via nginx stream) |
| SSH server key | `SHA256:E2ycjThOe09yMfERUKN76uDyW7YBT12rjS5FJXB+PZ4` (ED25519) |
| nginx stream routing | port 443: no-TLS → sshd:22, TLS → nginx:8443 |
| HTTPS services | Still accessible on port 443 (TLS SNI routing) |

---

## 9 — Security Notes

- Password authentication is currently enabled on VPS sshd for bootstrapping
- After confirming key-based login works from the restricted machine, ask the admin to disable password auth
- The nginx stream proxy does **not** terminate or inspect SSH sessions — it's a transparent TCP proxy
- `fail2ban` monitors both port 22 and 443 for brute-force attempts

---

*Last updated: 2026-04-18*  
*Implemented by: nginx stream `$ssl_preread_protocol` routing on VPS*  
*Related: `doc/research/vps-ssh-remote-access-proposal.md`*
