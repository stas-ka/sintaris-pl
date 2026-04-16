#!/usr/bin/env bash
# install-vps.sh — Initial VPS setup for agents.sintaris.net
#
# Target:   Ubuntu 24.04 LTS (dev2null.de / mail.dev2null.de)
# Services: nginx reverse proxy, PostgreSQL, SSH tunnel endpoints, Certbot SSL
# Run as:   stas (user with sudo) or root
# Usage:    bash install-vps.sh
#
# What this sets up:
#   - nginx with agents.sintaris.net config (reverse proxy for all taris instances)
#   - Let's Encrypt SSL certificate via Certbot
#   - PostgreSQL for CRM/EspoCRM data
#   - SSH authorized_keys for tunnel connections from taris targets
#   - Sintaris monitor systemd service (health checks)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOMAIN="agents.sintaris.net"

echo "=== 1. System packages ==="
sudo apt update
sudo apt install -y \
    nginx \
    certbot python3-certbot-nginx \
    postgresql postgresql-contrib \
    autossh \
    python3 python3-pip

echo "=== 2. nginx ==="
sudo cp "$SCRIPT_DIR/../system-configs/vps/nginx/agents.sintaris.net.conf" \
    /etc/nginx/sites-available/"$DOMAIN".conf
sudo ln -sf /etc/nginx/sites-available/"$DOMAIN".conf \
    /etc/nginx/sites-enabled/"$DOMAIN".conf
sudo nginx -t && sudo systemctl reload nginx

echo "=== 3. Let's Encrypt SSL ==="
sudo certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos \
    -m admin@sintaris.net
# SSL auto-renew is installed by certbot as a systemd timer

echo "=== 4. PostgreSQL for CRM ==="
sudo -u postgres psql <<'SQL'
CREATE USER taris WITH PASSWORD 'CHANGE_ME';
CREATE DATABASE taris OWNER taris;
GRANT ALL PRIVILEGES ON DATABASE taris TO taris;
SQL
# pg_hba.conf: ensure localhost connections allowed for 'taris' user
echo "  → Verify /etc/postgresql/*/main/pg_hba.conf allows 127.0.0.1/32 md5"

echo "=== 5. SSH tunnel authorized_keys ==="
echo "  → Add public keys from taris targets to ~/.ssh/authorized_keys:"
echo "  → Key from SintAItion: cat ~/.ssh/vps_tunnel_key.pub  (on SintAItion)"
echo "  → Key from TariStation2: cat ~/.ssh/vps_tunnel_key.pub  (on TariStation2)"
echo ""
echo "  Append with: cat key.pub >> ~/.ssh/authorized_keys"
echo "  Permissions: chmod 600 ~/.ssh/authorized_keys"

echo "=== 6. Sintaris monitor service ==="
sudo mkdir -p /opt/sintaris-monitor
# Deploy monitor.py (from project, not included here)
sudo cp "$SCRIPT_DIR/../system-configs/vps/systemd/sintaris-monitor.service" \
    /etc/systemd/system/
sudo cp "$SCRIPT_DIR/../system-configs/vps/systemd/sintaris-monitor.timer" \
    /etc/systemd/system/
sudo cp "$SCRIPT_DIR/../system-configs/vps/systemd/sintaris-monitor-daily.service" \
    /etc/systemd/system/
sudo cp "$SCRIPT_DIR/../system-configs/vps/systemd/sintaris-monitor-daily.timer" \
    /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sintaris-monitor.timer sintaris-monitor-daily.timer

echo ""
echo "=== VPS setup complete ==="
echo "Tunnel ports used by nginx:"
echo "  8082 → OpenClawPI  (/taris/)"
echo "  8084 → OpenClawPI2 (/taris2/)"
echo "  8086 → SintAItion  (/supertaris/)"
echo "  8088 → TariStation2 (/supertaris2/)"
echo ""
echo "SSH tunnels are opened from the TARGET machines (autossh), not from VPS."
echo "Verify active tunnels: ss -tlnp | grep -E '808[2468]'"
