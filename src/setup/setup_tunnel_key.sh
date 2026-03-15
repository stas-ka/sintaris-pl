#!/usr/bin/env bash
# setup_tunnel_key.sh — Generate SSH keypair and install autossh tunnel service
#
# Run on EACH Pi (as stas or with sudo):
#   bash setup_tunnel_key.sh
#
# What this does:
#   1. Installs autossh
#   2. Generates a dedicated ed25519 SSH key for the VPS tunnel
#   3. Prints the public key → paste it into install_vps.sh on the VPS
#   4. Copies the picoclaw-tunnel.service file and sets the correct port
#      (Pi1=8081, Pi2=8082, auto-detected from hostname)
#   5. Enables and starts the tunnel service

set -euo pipefail

PICOCLAW_DIR="/home/stas/.picoclaw"
SSH_KEY="/home/stas/.ssh/vps_tunnel_key"
SERVICE_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/services/picoclaw-tunnel.service"
HOSTNAME_VAL="$(hostname)"

# ── Load .env from repo root if available (dev machine or Pi with repo cloned) ─
ENV_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/.env"
if [[ -f "${ENV_FILE}" ]]; then
    # shellcheck disable=SC1090
    set -a; source "${ENV_FILE}"; set +a
    echo "Loaded config from ${ENV_FILE}"
fi
# Defaults if not set via .env
_VPS_HOST_DEFAULT="${VPS_DOMAIN:-agents.sintaris.net}"
_VPS_USER_DEFAULT="${VPS_BRIDGE_USER:-picobridge}"

# ── Detect which Pi this is running on ───────────────────────────────────────
if [[ "${HOSTNAME_VAL,,}" == *"pi2"* ]] || [[ "${HOSTNAME_VAL,,}" == "openclawpi2" ]]; then
    REMOTE_PORT=8082
    echo "Detected Pi2 (${HOSTNAME_VAL}) → VPS tunnel port 8082"
else
    REMOTE_PORT=8081
    echo "Detected Pi1 (${HOSTNAME_VAL}) → VPS tunnel port 8081"
fi

# ── Ask for VPS hostname if needed; default from .env ───────────────────────
echo ""
read -r -p "VPS hostname or IP for SSH [${_VPS_HOST_DEFAULT}]: " VPS_HOST_INPUT
VPS_HOST="${VPS_HOST_INPUT:-${_VPS_HOST_DEFAULT}}"
VPS_USER="${_VPS_USER_DEFAULT}"

# ── [1] Install autossh ───────────────────────────────────────────────────────
echo ""
echo "=== [1/4] Installing autossh ==="
sudo apt-get install -y autossh openssh-client

# ── [2] Generate SSH keypair ──────────────────────────────────────────────────
echo ""
echo "=== [2/4] Generating SSH key ==="
mkdir -p /home/stas/.ssh
chmod 700 /home/stas/.ssh

if [[ -f "${SSH_KEY}" ]]; then
    echo "  Key already exists at ${SSH_KEY} — skipping generation."
    echo "  Delete it first if you want to regenerate: rm ${SSH_KEY} ${SSH_KEY}.pub"
else
    ssh-keygen -t ed25519 -C "${HOSTNAME_VAL}-picoassist" -N "" -f "${SSH_KEY}"
    echo "  Key generated."
fi

# ── [3] Show public key ───────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  ▶ COPY THIS PUBLIC KEY — paste it into install_vps.sh on VPS"
echo "════════════════════════════════════════════════════════════════"
cat "${SSH_KEY}.pub"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "Paste the key into install_vps.sh when prompted for '${HOSTNAME_VAL} public key'"
echo ""
read -r -p "Press ENTER when you have added the key to the VPS..."

# ── [4] Create and install systemd service ────────────────────────────────────
echo ""
echo "=== [4/4] Installing picoclaw-tunnel.service ==="

# Use the service file from src/services/ if available, else download or fail
if [[ ! -f "${SERVICE_SRC}" ]]; then
    echo "  WARNING: service file not found at ${SERVICE_SRC}"
    echo "  Please ensure picoclaw-tunnel.service exists in src/services/"
    echo "  Then re-run this script."
    exit 1
fi

# Write tunnel.env for the systemd EnvironmentFile (overwrite with correct values)
TUNNEL_ENV="${PICOCLAW_DIR}/tunnel.env"
mkdir -p "${PICOCLAW_DIR}"
cat > "${TUNNEL_ENV}" <<EOF
VPS_HOST=${VPS_HOST}
VPS_USER=${VPS_USER}
REMOTE_PORT=${REMOTE_PORT}
LOCAL_PORT=8080
SSH_KEY=${SSH_KEY}
EOF
chmod 600 "${TUNNEL_ENV}"
echo "  Written ${TUNNEL_ENV}"

sudo cp "${SERVICE_SRC}" /etc/systemd/system/picoclaw-tunnel.service
sudo systemctl daemon-reload
sudo systemctl enable picoclaw-tunnel
sudo systemctl restart picoclaw-tunnel

echo ""
echo "═══════════════════════════════════════════════════════════"
echo " ✅  Tunnel service installed and started!"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "Check status:"
echo "  systemctl status picoclaw-tunnel"
echo "  journalctl -u picoclaw-tunnel -n 20 --no-pager"
echo ""
echo "After both Pis are connected, test from the internet:"
if [[ "${REMOTE_PORT}" == "8081" ]]; then
    echo "  curl -I https://agents.sintaris.net/picoassist/"
else
    echo "  curl -I https://agents.sintaris.net/picoassist2/"
fi
