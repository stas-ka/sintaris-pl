#!/usr/bin/env bash
# deploy_vps.sh — Deploy nginx reverse proxy to VPS from your dev machine
#
# Run from the repo root:
#   bash src/setup/deploy_vps.sh
#
# Prerequisites:
#   1. Fill in .env at the repo root (see the VPS section):
#        SSH_HOST         — VPS hostname or IP
#        SSH_USER         — your VPS user (sudo-capable)
#        SSH_PORT         — SSH port (usually 22)
#        SSH_KEY_PATH     — path to your SSH private key
#        VPS_DOMAIN       — domain for the nginx vhost (e.g. agents.sintaris.net)
#        VPS_BRIDGE_USER  — the restricted tunnel-only user to create (e.g. picobridge)
#        CERTBOT_EMAIL    — your email for Let's Encrypt notifications
#   2. DNS A record for VPS_DOMAIN must already point to the VPS public IP
#   3. You need sudo rights on the VPS via your SSH_USER

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"

# ── Load .env ─────────────────────────────────────────────────────────────────
if [[ ! -f "${ENV_FILE}" ]]; then
    echo "ERROR: .env not found at ${ENV_FILE}" >&2
    exit 1
fi
# shellcheck disable=SC1090
set -a; source "${ENV_FILE}"; set +a

# ── Validate required variables ───────────────────────────────────────────────
: "${SSH_HOST:?Set SSH_HOST in .env (VPS hostname or IP)}"
: "${SSH_USER:?Set SSH_USER in .env}"
: "${VPS_DOMAIN:?Set VPS_DOMAIN in .env (e.g. agents.sintaris.net)}"
: "${VPS_BRIDGE_USER:?Set VPS_BRIDGE_USER in .env (e.g. picobridge)}"
: "${CERTBOT_EMAIL:?Set CERTBOT_EMAIL in .env (your email for Lets Encrypt)}"

SSH_PORT="${SSH_PORT:-22}"
SSH_KEY_PATH="${SSH_KEY_PATH:-~/.ssh/id_ed25519}"

SSH_OPTS="-p ${SSH_PORT} -i ${SSH_KEY_PATH} -o StrictHostKeyChecking=accept-new"
SCP_OPTS="-P ${SSH_PORT} -i ${SSH_KEY_PATH} -o StrictHostKeyChecking=accept-new"
REMOTE="${SSH_USER}@${SSH_HOST}"
REMOTE_TMP="/tmp/taris-vps-setup"

echo ""
echo "═══════════════════════════════════════════════════════════"
echo " Deploying VPS nginx proxy for ${VPS_DOMAIN}"
echo " VPS: ${REMOTE} (port ${SSH_PORT})"
echo " Bridge user: ${VPS_BRIDGE_USER}"
echo "═══════════════════════════════════════════════════════════"
echo ""

# ── [1/3] Upload setup files to VPS ─────────────────────────────────────────
echo "=== [1/3] Uploading setup files to VPS ==="
ssh ${SSH_OPTS} "${REMOTE}" "mkdir -p ${REMOTE_TMP}"
scp ${SCP_OPTS} \
    "${REPO_ROOT}/src/setup/install_vps.sh" \
    "${REPO_ROOT}/src/setup/nginx-vps.conf" \
    "${REMOTE}:${REMOTE_TMP}/"
echo "  Files uploaded."

# ── [2/3] Run install_vps.sh on VPS ─────────────────────────────────────────
echo ""
echo "=== [2/3] Running install_vps.sh on VPS (this may take a few minutes) ==="
echo ""
ssh ${SSH_OPTS} "${REMOTE}" "export VPS_DOMAIN='${VPS_DOMAIN}' VPS_BRIDGE_USER='${VPS_BRIDGE_USER}' CERTBOT_EMAIL='${CERTBOT_EMAIL}' && sudo --preserve-env=VPS_DOMAIN,VPS_BRIDGE_USER,CERTBOT_EMAIL bash ${REMOTE_TMP}/install_vps.sh"

# ── [3/3] Cleanup ────────────────────────────────────────────────────────────
echo ""
echo "=== [3/3] Cleaning up temp files on VPS ==="
ssh ${SSH_OPTS} "${REMOTE}" "rm -rf ${REMOTE_TMP}"
echo "  Done."

echo ""
echo "═══════════════════════════════════════════════════════════"
echo " ✅  VPS deployment complete!"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "Next: run setup_tunnel_key.sh on EACH Pi, then test:"
echo "  curl -I https://${VPS_DOMAIN}/picoassist/"
echo "  curl -I https://${VPS_DOMAIN}/picoassist2/"
echo ""
echo "If a Pi is not yet tunnelled: 502 Bad Gateway is normal."
