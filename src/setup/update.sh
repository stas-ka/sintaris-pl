#!/bin/bash
# =============================================================================
# update.sh — Update Existing Pico Bot Installation  (§6.3.2)
# =============================================================================
# Re-deploys bot source files, restarts services, optionally upgrades picoclaw
# binary. Does NOT touch secrets (bot.env / config.json).
#
# Usage:
#   sudo bash update.sh [--upgrade-picoclaw]
#
# Run from the cloned project root directory (where src/ is), e.g.:
#   git pull && sudo bash src/setup/update.sh
# =============================================================================

set -euo pipefail

PICOCLAW_USER="stas"
PICOCLAW_DIR="/home/${PICOCLAW_USER}/.picoclaw"
SYSTEMD_DIR="/etc/systemd/system"
PICOCLAW_DEB_URL="https://github.com/sipeed/picoclaw/releases/latest/download/picoclaw_aarch64.deb"
UPGRADE_PICOCLAW=false

SCRIPT_DIR="$(dirname "$(realpath "${BASH_SOURCE[0]}")")"
SRC_DIR="$(realpath "${SCRIPT_DIR}/..")"

# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --upgrade-picoclaw) UPGRADE_PICOCLAW=true; shift ;;
    *) echo "[!] Unknown argument: $1"; exit 1 ;;
  esac
done

echo "=============================================="
echo " Pico Bot — Update"
echo "=============================================="
echo "  Source  : ${SRC_DIR}"
echo "  Pi dir  : ${PICOCLAW_DIR}"
echo ""

if [[ "$(id -u)" -ne 0 ]]; then
  echo "[!] Run as root: sudo bash $0"
  exit 1
fi

# ---------------------------------------------------------------------------
# Step 1 — Optionally upgrade picoclaw binary
# ---------------------------------------------------------------------------
if [[ "${UPGRADE_PICOCLAW}" == "true" ]]; then
  echo "[1/4] Upgrading picoclaw binary..."
  wget -q "${PICOCLAW_DEB_URL}" -O /tmp/picoclaw_aarch64.deb
  dpkg -i /tmp/picoclaw_aarch64.deb
  rm /tmp/picoclaw_aarch64.deb
  picoclaw version
  echo "  picoclaw upgraded."
else
  echo "[1/4] Skipping picoclaw upgrade (pass --upgrade-picoclaw to update)."
  picoclaw version 2>/dev/null || true
fi

# ---------------------------------------------------------------------------
# Step 1b — Ensure Python packages are up to date (including sqlite-vec)
# ---------------------------------------------------------------------------
echo ""
echo "[1b/4] Installing/upgrading Python packages..."
pip3 install --break-system-packages --quiet --upgrade sqlite-vec
echo "  sqlite-vec: $(python3 -c 'import sqlite_vec; print(sqlite_vec.__version__)' 2>/dev/null || echo 'not installed')"

# ---------------------------------------------------------------------------
# Step 2 — Deploy bot source files
# ---------------------------------------------------------------------------
echo ""
echo "[2/4] Deploying bot source files..."
for f in telegram_menu_bot.py gmail_digest.py voice_assistant.py \
          strings.json release_notes.json; do
  if [[ -f "${SRC_DIR}/${f}" ]]; then
    cp "${SRC_DIR}/${f}" "${PICOCLAW_DIR}/${f}"
    echo "  Deployed: ${f}"
  else
    echo "  [!] Not found (skip): ${SRC_DIR}/${f}"
  fi
done

chown -R "${PICOCLAW_USER}:${PICOCLAW_USER}" "${PICOCLAW_DIR}"

# ---------------------------------------------------------------------------
# Step 3 — Update systemd service files (if changed)
# ---------------------------------------------------------------------------
echo ""
echo "[3/4] Syncing systemd service files..."
SERVICES_DIR="${SRC_DIR}/services"
SERVICES=(picoclaw-gateway picoclaw-telegram picoclaw-voice)
RELOAD_NEEDED=false

for svc in "${SERVICES[@]}"; do
  SVC_FILE="${SERVICES_DIR}/${svc}.service"
  DEST="${SYSTEMD_DIR}/${svc}.service"
  if [[ -f "${SVC_FILE}" ]]; then
    if ! cmp -s "${SVC_FILE}" "${DEST}" 2>/dev/null; then
      cp "${SVC_FILE}" "${DEST}"
      echo "  Updated: ${svc}.service"
      RELOAD_NEEDED=true
    else
      echo "  Unchanged: ${svc}.service"
    fi
  fi
done

if [[ "${RELOAD_NEEDED}" == "true" ]]; then
  systemctl daemon-reload
  echo "  systemd daemon reloaded."
fi

# ---------------------------------------------------------------------------
# Step 4 — Restart active services
# ---------------------------------------------------------------------------
echo ""
echo "[4/4] Restarting picoclaw services..."
RESTART_FAILED=false

for svc in "${SERVICES[@]}"; do
  if systemctl is-active --quiet "${svc}" 2>/dev/null; then
    systemctl restart "${svc}"
    echo "  Restarted: ${svc}"
  elif systemctl is-enabled --quiet "${svc}" 2>/dev/null; then
    systemctl start "${svc}" || RESTART_FAILED=true
    echo "  Started: ${svc}"
  else
    echo "  Skipped (not enabled): ${svc}"
  fi
done

sleep 3

# ---------------------------------------------------------------------------
echo ""
echo "=============================================="
echo " Update complete."
echo "=============================================="
echo ""
echo "Service status:"
for svc in "${SERVICES[@]}"; do
  STATUS=$(systemctl is-active "${svc}" 2>/dev/null || echo "inactive")
  echo "  ${svc}: ${STATUS}"
done

if [[ "${RESTART_FAILED}" == "true" ]]; then
  echo ""
  echo "[!] One or more services failed to start. Check:"
  echo "    journalctl -u picoclaw-telegram -n 20 --no-pager"
fi
