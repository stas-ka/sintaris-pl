#!/bin/bash
# =============================================================================
# update_from_cloud.sh — Update Taris Bot from cloud.dev2null.de
# =============================================================================
# Downloads the latest release package from the deploy server and applies it.
# Safe: verifies checksum, backs up current files, and can roll back on failure.
#
# Usage (as root on the Pi):
#   sudo bash update_from_cloud.sh [--force] [--check]
#
# Options:
#   --force   Apply update even if version matches
#   --check   Only print available version, do not update
#
# Config (read from bot.env or environment):
#   CLOUD_DEPLOY_URL   Base URL on the cloud server (default below)
#   CLOUD_DEPLOY_TOKEN Optional Bearer token for private endpoints
# =============================================================================

set -euo pipefail

# ── defaults ─────────────────────────────────────────────────────────────────
TARIS_USER="${TARIS_USER:-stas}"
TARIS_DIR="/home/${TARIS_USER}/.taris"
SYSTEMD_DIR="/etc/systemd/system"
BACKUP_DIR="/tmp/taris-backup"

CLOUD_DEPLOY_URL="${CLOUD_DEPLOY_URL:-https://cloud.dev2null.de/taris}"
CLOUD_DEPLOY_TOKEN="${CLOUD_DEPLOY_TOKEN:-}"

FORCE=false
CHECK_ONLY=false

# ── colours ───────────────────────────────────────────────────────────────────
G="\e[32m"; Y="\e[33m"; R="\e[31m"; B="\e[34m"; N="\e[0m"
ok()   { echo -e "${G}[OK]${N}  $*"; }
info() { echo -e "${B}[..]${N}  $*"; }
warn() { echo -e "${Y}[!]${N}   $*"; }
fail() { echo -e "${R}[FAIL]${N} $*"; exit 1; }

# ── args ──────────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --force)  FORCE=true;      shift ;;
    --check)  CHECK_ONLY=true; shift ;;
    *) warn "Unknown argument: $1"; shift ;;
  esac
done

# ── root check ────────────────────────────────────────────────────────────────
[[ "${CHECK_ONLY}" == "false" && "$(id -u)" -ne 0 ]] && \
  fail "Run as root: sudo bash $0"

# ── load bot.env for optional CLOUD_DEPLOY_URL override ──────────────────────
if [[ -f "${TARIS_DIR}/bot.env" ]]; then
  # shellcheck disable=SC1091
  source <(grep -E '^(CLOUD_DEPLOY_URL|CLOUD_DEPLOY_TOKEN)=' \
    "${TARIS_DIR}/bot.env" 2>/dev/null || true)
fi

echo ""
echo "=============================================="
echo "  Taris Bot — Update from Cloud"
echo "=============================================="
echo "  Server : ${CLOUD_DEPLOY_URL}"
echo ""

# ── curl helper (adds auth header if token is set) ────────────────────────────
_curl() {
  local args=(-fsSL --max-time 30)
  [[ -n "${CLOUD_DEPLOY_TOKEN}" ]] && \
    args+=(-H "Authorization: Bearer ${CLOUD_DEPLOY_TOKEN}")
  curl "${args[@]}" "$@"
}

# ── Step 1: fetch available version ──────────────────────────────────────────
info "Fetching version info from server..."
AVAILABLE_VERSION=$(_curl "${CLOUD_DEPLOY_URL}/version.txt" | tr -d '[:space:]') \
  || fail "Cannot reach ${CLOUD_DEPLOY_URL}/version.txt — is the server up?"

INSTALLED_VERSION="none"
if [[ -f "${TARIS_DIR}/installed_version.txt" ]]; then
  INSTALLED_VERSION=$(cat "${TARIS_DIR}/installed_version.txt" | tr -d '[:space:]')
fi

echo "  Installed : ${INSTALLED_VERSION}"
echo "  Available : ${AVAILABLE_VERSION}"
echo ""

if [[ "${CHECK_ONLY}" == "true" ]]; then
  if [[ "${AVAILABLE_VERSION}" == "${INSTALLED_VERSION}" ]]; then
    ok "Up to date (${INSTALLED_VERSION})"
  else
    warn "Update available: ${INSTALLED_VERSION} → ${AVAILABLE_VERSION}"
  fi
  exit 0
fi

if [[ "${AVAILABLE_VERSION}" == "${INSTALLED_VERSION}" && "${FORCE}" == "false" ]]; then
  ok "Already up to date (${INSTALLED_VERSION}). Use --force to reinstall."
  exit 0
fi

# ── Step 2: download package ──────────────────────────────────────────────────
PKG_NAME="taris-bot.tar.gz"
PKG_URL="${CLOUD_DEPLOY_URL}/${PKG_NAME}"
PKG_PATH="/tmp/${PKG_NAME}"
SHA_URL="${PKG_URL}.sha256"

info "Downloading ${PKG_NAME}..."
_curl "${PKG_URL}" -o "${PKG_PATH}" \
  || fail "Download failed: ${PKG_URL}"
ok "Downloaded $(du -sh ${PKG_PATH} | cut -f1)"

# ── Step 3: verify checksum ──────────────────────────────────────────────────
EXPECTED_SHA=$(_curl "${SHA_URL}" | awk '{print $1}') \
  || { warn "No .sha256 file — skipping checksum verification"; EXPECTED_SHA=""; }

if [[ -n "${EXPECTED_SHA}" ]]; then
  ACTUAL_SHA=$(sha256sum "${PKG_PATH}" | awk '{print $1}')
  if [[ "${ACTUAL_SHA}" != "${EXPECTED_SHA}" ]]; then
    fail "Checksum mismatch! Expected ${EXPECTED_SHA}, got ${ACTUAL_SHA}"
  fi
  ok "Checksum OK"
fi

# ── Step 4: back up existing bot files ──────────────────────────────────────
info "Backing up current installation to ${BACKUP_DIR}..."
rm -rf "${BACKUP_DIR}" && mkdir -p "${BACKUP_DIR}"
BOT_FILES=(
  telegram_menu_bot.py bot_config.py bot_state.py bot_instance.py
  bot_security.py bot_access.py bot_users.py bot_voice.py bot_calendar.py
  bot_admin.py bot_handlers.py bot_mail_creds.py bot_email.py
  gmail_digest.py voice_assistant.py strings.json release_notes.json
  installed_version.txt
)
for f in "${BOT_FILES[@]}"; do
  [[ -f "${TARIS_DIR}/${f}" ]] && cp "${TARIS_DIR}/${f}" "${BACKUP_DIR}/"
done

if [[ -d "${SYSTEMD_DIR}" ]]; then
  for svc in taris-telegram taris-voice; do
    [[ -f "${SYSTEMD_DIR}/${svc}.service" ]] && \
      cp "${SYSTEMD_DIR}/${svc}.service" "${BACKUP_DIR}/"
  done
fi
ok "Backed up to ${BACKUP_DIR}"

# ── Step 5: extract and apply ─────────────────────────────────────────────────
info "Extracting package..."
EXTRACT_DIR="/tmp/taris-update"
rm -rf "${EXTRACT_DIR}" && mkdir -p "${EXTRACT_DIR}"
tar -xzf "${PKG_PATH}" -C "${EXTRACT_DIR}" \
  || fail "Failed to extract ${PKG_PATH}"

# Locate the src directory inside the tarball (may be top-level or one level deep)
SRC_IN_PKG="${EXTRACT_DIR}"
if [[ -d "${EXTRACT_DIR}/src" ]]; then
  SRC_IN_PKG="${EXTRACT_DIR}/src"
elif [[ -d "${EXTRACT_DIR}/taris/src" ]]; then
  SRC_IN_PKG="${EXTRACT_DIR}/taris/src"
fi

info "Deploying bot files to ${TARIS_DIR}..."
for f in telegram_menu_bot.py bot_config.py bot_state.py bot_instance.py \
          bot_security.py bot_access.py bot_users.py bot_voice.py bot_calendar.py \
          bot_admin.py bot_handlers.py bot_mail_creds.py bot_email.py \
          gmail_digest.py voice_assistant.py strings.json release_notes.json; do
  SRC="${SRC_IN_PKG}/${f}"
  if [[ -f "${SRC}" ]]; then
    cp "${SRC}" "${TARIS_DIR}/${f}"
    info "  → ${f}"
  else
    warn "  Not in package: ${f}"
  fi
done

# service files
RELOAD_NEEDED=false
SERVICES_IN_PKG="${SRC_IN_PKG}/services"
if [[ -d "${SERVICES_IN_PKG}" ]]; then
  for svc in taris-telegram taris-voice; do
    SVC_SRC="${SERVICES_IN_PKG}/${svc}.service"
    SVC_DST="${SYSTEMD_DIR}/${svc}.service"
    if [[ -f "${SVC_SRC}" ]]; then
      if ! cmp -s "${SVC_SRC}" "${SVC_DST}" 2>/dev/null; then
        cp "${SVC_SRC}" "${SVC_DST}"
        RELOAD_NEEDED=true
        info "  → ${svc}.service (updated)"
      fi
    fi
  done
fi

# mark installed version
echo "${AVAILABLE_VERSION}" > "${TARIS_DIR}/installed_version.txt"
chown -R "${TARIS_USER}:${TARIS_USER}" "${TARIS_DIR}"
ok "Files deployed"

# ── Step 6: reload + restart services ─────────────────────────────────────────
info "Restarting services..."
[[ "${RELOAD_NEEDED}" == "true" ]] && systemctl daemon-reload

FAILED=false
for svc in taris-telegram taris-voice; do
  if systemctl is-active --quiet "${svc}" 2>/dev/null || \
     systemctl is-enabled --quiet "${svc}" 2>/dev/null; then
    if ! systemctl restart "${svc}" 2>/dev/null; then
      warn "Failed to restart ${svc} — rolling back"
      FAILED=true
      break
    fi
    ok "Restarted ${svc}"
  fi
done

# ── rollback on failure ───────────────────────────────────────────────────────
if [[ "${FAILED}" == "true" ]]; then
  warn "Applying rollback from ${BACKUP_DIR}..."
  cp "${BACKUP_DIR}"/*.py "${BACKUP_DIR}"/*.json "${TARIS_DIR}/" 2>/dev/null || true
  [[ -f "${BACKUP_DIR}/installed_version.txt" ]] && \
    cp "${BACKUP_DIR}/installed_version.txt" "${TARIS_DIR}/"
  for svc in taris-telegram taris-voice; do
    [[ -f "${BACKUP_DIR}/${svc}.service" ]] && \
      cp "${BACKUP_DIR}/${svc}.service" "${SYSTEMD_DIR}/"
  done
  systemctl daemon-reload
  for svc in taris-telegram taris-voice; do
    systemctl restart "${svc}" 2>/dev/null || true
  done
  fail "Update failed — rolled back to ${INSTALLED_VERSION}"
fi

# ── cleanup ────────────────────────────────────────────────────────────────────
rm -f "${PKG_PATH}"
rm -rf "${EXTRACT_DIR}"

# ── verify ────────────────────────────────────────────────────────────────────
echo ""
sleep 3
journalctl -u taris-telegram -n 5 --no-pager 2>/dev/null | \
  grep -E 'Version|Polling|ERROR' || true

echo ""
echo "=============================================="
ok "Update complete: ${INSTALLED_VERSION} → ${AVAILABLE_VERSION}"
echo "=============================================="
