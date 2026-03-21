#!/bin/bash
# =============================================================================
# publish_release.sh — Package and Upload Bot Release to cloud.dev2null.de
# =============================================================================
# Run this on your Windows dev machine (Git Bash / WSL) after committing changes.
#
# What it does:
#   1. Reads BOT_VERSION from src/bot_config.py
#   2. Packages all bot source files into taris-bot.tar.gz
#   3. Generates SHA256 checksum
#   4. Uploads package + version.txt + checksum to cloud.dev2null.de
#
# Requirements:
#   - .env in the repo root with CLOUD_* variables (see below)
#   - SSH key OR password access to the cloud server
#   - curl + tar + sha256sum available (Git Bash has these)
#
# .env variables needed:
#   CLOUD_HOST        cloud.dev2null.de
#   CLOUD_USER        username for SSH login
#   CLOUD_PWD         password (if no SSH key)
#   CLOUD_DEPLOY_PATH /path/on/server/to/taris/web/dir
#   CLOUD_DEPLOY_URL  https://cloud.dev2null.de/taris  (for verify step)
#   CLOUD_SSH_KEY     (optional) path to private key file
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SRC_DIR="${REPO_ROOT}/src"
WORKSPACE_ENV="${REPO_ROOT}/.env"

# ── colours ───────────────────────────────────────────────────────────────────
G="\033[32m"; Y="\033[33m"; R="\033[31m"; B="\033[34m"; N="\033[0m"
ok()   { echo -e "${G}[OK]${N}  $*"; }
info() { echo -e "${B}[..]${N}  $*"; }
warn() { echo -e "${Y}[!]${N}   $*"; }
fail() { echo -e "${R}[ERROR]${N} $*"; exit 1; }

# ── load .env ─────────────────────────────────────────────────────────────────
[[ -f "${WORKSPACE_ENV}" ]] && source "${WORKSPACE_ENV}" || \
  fail ".env not found at ${WORKSPACE_ENV}"

CLOUD_HOST="${CLOUD_HOST:-cloud.dev2null.de}"
CLOUD_USER="${CLOUD_USER:-}"
CLOUD_PWD="${CLOUD_PWD:-}"
CLOUD_DEPLOY_PATH="${CLOUD_DEPLOY_PATH:-/var/www/html/taris}"
CLOUD_DEPLOY_URL="${CLOUD_DEPLOY_URL:-https://${CLOUD_HOST}/taris}"
CLOUD_SSH_KEY="${CLOUD_SSH_KEY:-}"

[[ -z "${CLOUD_USER}" ]]        && fail "CLOUD_USER not set in .env"
[[ -z "${CLOUD_DEPLOY_PATH}" ]] && fail "CLOUD_DEPLOY_PATH not set in .env"

# ── Step 1: read BOT_VERSION ──────────────────────────────────────────────────
BOT_VERSION=$(grep -m1 'BOT_VERSION' "${SRC_DIR}/bot_config.py" \
  | sed 's/.*"\(.*\)".*/\1/')
[[ -z "${BOT_VERSION}" ]] && fail "Could not read BOT_VERSION from bot_config.py"

PKG_NAME="taris-bot.tar.gz"
PKG_PATH="${REPO_ROOT}/deploy/${PKG_NAME}"
mkdir -p "${REPO_ROOT}/deploy"

echo ""
echo "=============================================="
echo "  Taris Bot — Publish Release"
echo "=============================================="
echo "  Version : ${BOT_VERSION}"
echo "  Server  : ${CLOUD_USER}@${CLOUD_HOST}:${CLOUD_DEPLOY_PATH}"
echo "  URL     : ${CLOUD_DEPLOY_URL}"
echo ""

# ── Step 2: package bot files ─────────────────────────────────────────────────
BOT_FILES=(
  bot_config.py bot_state.py bot_instance.py bot_security.py bot_access.py
  bot_users.py bot_voice.py bot_calendar.py bot_admin.py bot_handlers.py
  bot_mail_creds.py bot_email.py gmail_digest.py voice_assistant.py
  telegram_menu_bot.py strings.json release_notes.json
)

info "Creating package ${PKG_NAME}..."
# Build tar from SRC_DIR with services sub-dir
cd "${REPO_ROOT}"

TAR_ARGS=()
for f in "${BOT_FILES[@]}"; do
  FILE_PATH="src/${f}"
  if [[ -f "${FILE_PATH}" ]]; then
    TAR_ARGS+=("${FILE_PATH}")
  else
    warn "  Missing (skip): ${FILE_PATH}"
  fi
done

# Add services directory
[[ -d "src/services" ]] && TAR_ARGS+=("src/services")

tar -czf "${PKG_PATH}" "${TAR_ARGS[@]}"
PKG_SIZE=$(du -sh "${PKG_PATH}" | cut -f1)
ok "Package created: ${PKG_PATH} (${PKG_SIZE})"

# ── Step 3: generate checksum ────────────────────────────────────────────────
info "Generating SHA256 checksum..."
SHA_FILE="${PKG_PATH}.sha256"
sha256sum "${PKG_PATH}" > "${SHA_FILE}"
SHA_VALUE=$(awk '{print $1}' "${SHA_FILE}")
ok "SHA256: ${SHA_VALUE:0:16}..."

# Write version file
echo "${BOT_VERSION}" > "${REPO_ROOT}/deploy/version.txt"

# ── Step 4: upload to cloud server ───────────────────────────────────────────
info "Uploading to ${CLOUD_HOST}..."

# Build SSH options
SSH_OPTS=(-o StrictHostKeyChecking=accept-new -o BatchMode=no)
SCP_OPTS=(-o StrictHostKeyChecking=accept-new)
if [[ -n "${CLOUD_SSH_KEY}" && -f "${CLOUD_SSH_KEY}" ]]; then
  SSH_OPTS+=(-i "${CLOUD_SSH_KEY}")
  SCP_OPTS+=(-i "${CLOUD_SSH_KEY}")
fi

# Upload function — tries SSH key first, then sshpass if password given
_scp() {
  local src="$1"; local dst="${CLOUD_USER}@${CLOUD_HOST}:${CLOUD_DEPLOY_PATH}/$2"
  if [[ -n "${CLOUD_SSH_KEY}" && -f "${CLOUD_SSH_KEY}" ]]; then
    scp "${SCP_OPTS[@]}" "${src}" "${dst}"
  elif command -v sshpass >/dev/null 2>&1 && [[ -n "${CLOUD_PWD}" ]]; then
    sshpass -p "${CLOUD_PWD}" scp "${SCP_OPTS[@]}" "${src}" "${dst}"
  elif command -v pscp >/dev/null 2>&1 && [[ -n "${CLOUD_PWD}" ]]; then
    pscp -pw "${CLOUD_PWD}" -batch "${src}" "${dst}"
  else
    fail "No upload method available. Set CLOUD_SSH_KEY, install sshpass, or ensure pscp is in PATH."
  fi
}

# Ensure remote directory exists
_ssh_cmd() {
  if [[ -n "${CLOUD_SSH_KEY}" && -f "${CLOUD_SSH_KEY}" ]]; then
    ssh "${SSH_OPTS[@]}" "${CLOUD_USER}@${CLOUD_HOST}" "$@"
  elif command -v sshpass >/dev/null 2>&1 && [[ -n "${CLOUD_PWD}" ]]; then
    sshpass -p "${CLOUD_PWD}" ssh "${SSH_OPTS[@]}" "${CLOUD_USER}@${CLOUD_HOST}" "$@"
  elif command -v plink >/dev/null 2>&1 && [[ -n "${CLOUD_PWD}" ]]; then
    plink -pw "${CLOUD_PWD}" -batch "${CLOUD_USER}@${CLOUD_HOST}" "$@"
  else
    fail "No SSH method available."
  fi
}

_ssh_cmd "mkdir -p '${CLOUD_DEPLOY_PATH}'"

info "  Uploading ${PKG_NAME}..."
_scp "${PKG_PATH}" "${PKG_NAME}"
info "  Uploading ${PKG_NAME}.sha256..."
_scp "${SHA_FILE}" "${PKG_NAME}.sha256"
info "  Uploading version.txt..."
_scp "${REPO_ROOT}/deploy/version.txt" "version.txt"
ok "Upload complete"

# ── Step 5: verify endpoint is reachable ─────────────────────────────────────
info "Verifying endpoint..."
sleep 2
REMOTE_VERSION=$(curl -fsS --max-time 10 "${CLOUD_DEPLOY_URL}/version.txt" \
  | tr -d '[:space:]') || { warn "Could not verify endpoint (HTTPS may need a moment)"; REMOTE_VERSION=""; }

if [[ "${REMOTE_VERSION}" == "${BOT_VERSION}" ]]; then
  ok "Verified: ${CLOUD_DEPLOY_URL}/version.txt → ${REMOTE_VERSION}"
else
  warn "Endpoint returned '${REMOTE_VERSION}' (expected '${BOT_VERSION}')"
  warn "Check web server config for ${CLOUD_DEPLOY_PATH}"
fi

# ── print Pi update command ───────────────────────────────────────────────────
echo ""
echo "=============================================="
ok "Release ${BOT_VERSION} published!"
echo ""
echo "  Update Pi1:  plink -pw \"\$HOSTPWD\" -batch stas@OpenClawPI \\"
echo "    \"sudo bash /home/stas/.taris/update_from_cloud.sh\""
echo ""
echo "  Update Pi2:  plink -pw \"\$TARGET2PWD\" -batch stas@OpenClawPI2 \\"
echo "    \"sudo bash /home/stas/.taris/update_from_cloud.sh\""
echo ""
echo "  Or on the Pi directly:"
echo "    sudo bash ~/.taris/update_from_cloud.sh"
echo "=============================================="
