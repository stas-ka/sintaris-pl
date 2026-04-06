#!/usr/bin/env bash
# =============================================================================
# install_picoclaw.sh — Full Fresh Install of Taris on PicoClaw (Raspberry Pi)
# =============================================================================
# Bootstraps a Raspberry Pi OS (Bookworm, aarch64) into a fully working Taris
# PicoClaw installation: picoclaw binary, Telegram bot, voice assistant
# (Vosk STT + Piper TTS), systemd services, and all Python packages.
#
# Run ONCE on a freshly imaged Pi as root:
#   sudo bash install_picoclaw.sh [options]
#
# Or deploy the script to the Pi first then run:
#   scp src/setup/install_picoclaw.sh stas@OpenClawPI2.local:/tmp/
#   ssh stas@OpenClawPI2.local "sudo bash /tmp/install_picoclaw.sh"
#
# Options:
#   --user <name>    Pi username (default: stas)
#   --voice          Install Vosk STT + Piper TTS (default: yes)
#   --no-voice       Skip voice pipeline install
#   --upgrade-picoclaw  Download and install latest picoclaw binary from GitHub
#   --no-picoclaw    Skip picoclaw binary install (if already installed)
#   --yes            Skip confirmation prompts
#   -h, --help
# =============================================================================

set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────────────
G="\033[32m"; Y="\033[33m"; R="\033[31m"; B="\033[34m"; C="\033[36m"; N="\033[0m"
ok()    { echo -e "${G}[OK]${N}   $*"; }
info()  { echo -e "${B}[..]${N}   $*"; }
warn()  { echo -e "${Y}[!]${N}    $*"; }
fail()  { echo -e "${R}[FAIL]${N} $*"; exit 1; }
hdr()   { echo -e "\n${C}━━━  $*  ━━━${N}"; }
ask()   { printf "${Y}[?]${N}    $* [y/N] "; read -r _ANS; [[ "${_ANS,,}" == y* ]]; }
ask_yn(){ printf "${Y}[?]${N}    $* [Y/n] "; read -r _ANS; [[ "${_ANS,,}" != n* ]]; }
prompt(){ printf "${Y}[?]${N}    $*: "; read -r _VAL; echo "$_VAL"; }

# ── Locate project root / source ─────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# When run from /tmp on Pi, SRC_DIR may not exist — we deploy from SCRIPT_DIR
SRC_DIR="$(realpath "${SCRIPT_DIR}/.." 2>/dev/null || echo "${SCRIPT_DIR}")"

# ── Defaults ─────────────────────────────────────────────────────────────────
TARIS_USER="${TARIS_USER:-stas}"
INSTALL_VOICE=true
INSTALL_PICOCLAW=true
YES=false

PICOCLAW_ARCH=$(uname -m)
PICOCLAW_DEB_URL="https://github.com/sipeed/picoclaw/releases/latest/download/picoclaw_${PICOCLAW_ARCH}.deb"
VOSK_MODEL_URL="https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip"
PIPER_VERSION="1.2.0"
PIPER_URL="https://github.com/rhasspy/piper/releases/download/${PIPER_VERSION}/piper_linux_${PICOCLAW_ARCH}.tar.gz"
PIPER_VOICE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx"

TARIS_DIR="/home/${TARIS_USER}/.taris"
SYSTEMD_DIR="/etc/systemd/system"

# ── Root check ────────────────────────────────────────────────────────────────
[[ "$(id -u)" -ne 0 ]] && fail "Run as root: sudo bash $0"

# ── Args ──────────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --user)          TARIS_USER="$2"; shift 2 ;;
    --voice)         INSTALL_VOICE=true; shift ;;
    --no-voice)      INSTALL_VOICE=false; shift ;;
    --upgrade-picoclaw|--picoclaw) INSTALL_PICOCLAW=true; shift ;;
    --no-picoclaw)   INSTALL_PICOCLAW=false; shift ;;
    --yes|-y)        YES=true; shift ;;
    -h|--help)
      sed -n '2,35p' "${BASH_SOURCE[0]}" | grep '^#' | sed 's/^# *//'
      exit 0 ;;
    *) warn "Unknown option: $1"; shift ;;
  esac
done

TARIS_DIR="/home/${TARIS_USER}/.taris"

# ── Architecture check ────────────────────────────────────────────────────────
ARCH=$(uname -m)
[[ "$ARCH" == "aarch64" || "$ARCH" == "armv7l" ]] || \
  warn "Unexpected architecture: ${ARCH}. Expected aarch64 (Pi). Continuing anyway."

# ── Header ────────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║   Taris Bot — PicoClaw (Raspberry Pi) Fresh Install     ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo "  Pi user   : ${TARIS_USER}"
echo "  Taris dir : ${TARIS_DIR}"
echo "  Arch      : ${ARCH}"
echo "  PicoClaw  : ${INSTALL_PICOCLAW}"
echo "  Voice     : ${INSTALL_VOICE}"
echo ""
if [[ "$YES" == false ]]; then
  ask_yn "Proceed with installation?" || { echo "Aborted."; exit 0; }
fi

# ── Step 1: System packages ───────────────────────────────────────────────────
hdr "Step 1/9 — System packages"
apt-get update -qq
apt-get install -y \
  python3 python3-pip git curl wget \
  ffmpeg portaudio19-dev espeak-ng \
  build-essential zstd unzip cron
ok "System packages installed"

# ── Step 2: Python packages ───────────────────────────────────────────────────
hdr "Step 2/9 — Python packages"
PIP="pip3 install --break-system-packages --quiet"

# Core + Telegram
$PIP pyTelegramBotAPI

# Voice (PicoClaw: Vosk STT + Piper TTS; no faster-whisper)
if [[ "$INSTALL_VOICE" == true ]]; then
  $PIP vosk sounddevice webrtcvad scipy
fi

# Gmail digest
$PIP google-api-python-client google-auth-httplib2 google-auth-oauthlib

# Web UI
$PIP fastapi "uvicorn[standard]" jinja2 bcrypt PyJWT python-multipart requests

# Storage + embeddings
$PIP fastembed pyyaml jsonschema pdfminer.six python-docx sqlite-vec

# Check requirements file if available
REQ="${SRC_DIR}/../../deploy/requirements.txt"
if [[ -f "$REQ" ]]; then
  $PIP -r "$REQ" 2>/dev/null || warn "Some packages from requirements.txt failed — continuing"
fi

ok "Python packages installed"

# ── Step 3: PicoClaw binary ──────────────────────────────────────────────────
hdr "Step 3/9 — PicoClaw binary"
if [[ "$INSTALL_PICOCLAW" == false ]]; then
  warn "Skipping picoclaw install (--no-picoclaw)"
  picoclaw version 2>/dev/null || warn "picoclaw not found in PATH"
elif picoclaw version &>/dev/null && [[ "$YES" == false ]] && ask_yn "PicoClaw already installed. Upgrade?"; then
  wget -q "${PICOCLAW_DEB_URL}" -O /tmp/picoclaw.deb
  dpkg -i /tmp/picoclaw.deb; rm /tmp/picoclaw.deb
  ok "PicoClaw upgraded: $(picoclaw version 2>/dev/null)"
elif ! picoclaw version &>/dev/null; then
  info "Downloading picoclaw binary..."
  wget -q "${PICOCLAW_DEB_URL}" -O /tmp/picoclaw.deb
  dpkg -i /tmp/picoclaw.deb; rm /tmp/picoclaw.deb
  ok "PicoClaw installed: $(picoclaw version 2>/dev/null)"
else
  ok "PicoClaw unchanged: $(picoclaw version 2>/dev/null)"
fi

# ── Step 4: Piper TTS ────────────────────────────────────────────────────────
hdr "Step 4/9 — Piper TTS"
if [[ "$INSTALL_VOICE" == false ]]; then
  warn "Skipping Piper TTS (--no-voice)"
else
  PIPER_DIR="${TARIS_DIR}/piper"
  if [[ -f "${PIPER_DIR}/piper" ]]; then
    ok "Piper already installed at ${PIPER_DIR}/piper"
  else
    info "Downloading Piper ${PIPER_VERSION} (${ARCH})..."
    mkdir -p "${PIPER_DIR}"
    wget -q "${PIPER_URL}" -O /tmp/piper.tar.gz
    tar -xzf /tmp/piper.tar.gz -C "${PIPER_DIR}" --strip-components=1
    rm /tmp/piper.tar.gz
    chown -R "${TARIS_USER}:${TARIS_USER}" "${PIPER_DIR}"
    ok "Piper installed at ${PIPER_DIR}/piper"
  fi

  # Piper Russian voice model
  PIPER_ONNX="${TARIS_DIR}/ru_RU-irina-medium.onnx"
  if [[ -f "$PIPER_ONNX" ]]; then
    ok "Piper Russian voice model already present"
  else
    info "Downloading Piper Russian voice model (Irina medium)..."
    sudo -u "${TARIS_USER}" wget -q "${PIPER_VOICE_URL}" -O "${PIPER_ONNX}"
    sudo -u "${TARIS_USER}" wget -q "${PIPER_VOICE_URL}.json" -O "${PIPER_ONNX}.json" 2>/dev/null || true
    ok "Piper voice model downloaded"
  fi
fi

# ── Step 5: Vosk STT model ───────────────────────────────────────────────────
hdr "Step 5/9 — Vosk STT model"
if [[ "$INSTALL_VOICE" == false ]]; then
  warn "Skipping Vosk model (--no-voice)"
else
  VOSK_DIR="${TARIS_DIR}/vosk-model-small-ru-0.22"
  if [[ -d "$VOSK_DIR" ]]; then
    ok "Vosk model already present at ${VOSK_DIR}"
  else
    info "Downloading Vosk Russian model (small, ~40 MB)..."
    TMP_ZIP=$(mktemp /tmp/vosk-XXXXXX.zip)
    sudo -u "${TARIS_USER}" wget -q "${VOSK_MODEL_URL}" -O "${TMP_ZIP}"
    sudo -u "${TARIS_USER}" unzip -q "${TMP_ZIP}" -d "${TARIS_DIR}/"
    rm -f "${TMP_ZIP}"
    # Rename to canonical name if needed
    [[ -d "${TARIS_DIR}/vosk-model-small-ru-0.22" ]] || \
      mv "${TARIS_DIR}/vosk-model-small-ru-"* "${VOSK_DIR}" 2>/dev/null || true
    ok "Vosk model downloaded to ${VOSK_DIR}"
  fi
fi

# ── Step 6: Taris directory + deploy source files ────────────────────────────
hdr "Step 6/9 — Deploy source files"
mkdir -p "${TARIS_DIR}"
for d in core telegram features ui security tests/voice/results \
          screens web/templates web/static calendar notes contacts \
          error_protocols mail_creds; do
  mkdir -p "${TARIS_DIR}/${d}"
done
for pkg in core telegram features ui security; do
  touch "${TARIS_DIR}/${pkg}/__init__.py"
done

if [[ -d "${SRC_DIR}" ]]; then
  for pkg in core telegram features ui security; do
    [[ -d "${SRC_DIR}/${pkg}" ]] && \
      cp "${SRC_DIR}/${pkg}/"*.py "${TARIS_DIR}/${pkg}/" && info "  ${pkg}/*.py" || true
  done
  for f in bot_web.py telegram_menu_bot.py voice_assistant.py gmail_digest.py; do
    [[ -f "${SRC_DIR}/${f}" ]] && cp "${SRC_DIR}/${f}" "${TARIS_DIR}/${f}" && info "  ${f}" || true
  done
  [[ -f "${SRC_DIR}/strings.json" ]] && cp "${SRC_DIR}/strings.json" "${TARIS_DIR}/"
  [[ -f "${SRC_DIR}/release_notes.json" ]] && cp "${SRC_DIR}/release_notes.json" "${TARIS_DIR}/"
  [[ -d "${SRC_DIR}/screens" ]] && cp -r "${SRC_DIR}/screens/." "${TARIS_DIR}/screens/"
  [[ -d "${SRC_DIR}/web/templates" ]] && cp -r "${SRC_DIR}/web/templates/." "${TARIS_DIR}/web/templates/"
  [[ -d "${SRC_DIR}/web/static" ]] && cp -r "${SRC_DIR}/web/static/." "${TARIS_DIR}/web/static/"
  [[ -d "${SRC_DIR}/tests" ]] && cp -r "${SRC_DIR}/tests/." "${TARIS_DIR}/tests/"
  ok "Source files deployed from ${SRC_DIR}"
else
  warn "Source directory ${SRC_DIR} not found — skipping source deploy"
  warn "Copy source files manually to ${TARIS_DIR}/"
fi

chown -R "${TARIS_USER}:${TARIS_USER}" "${TARIS_DIR}"

# ── Step 7: bot.env configuration ────────────────────────────────────────────
hdr "Step 7/9 — Bot configuration (bot.env)"
BOT_ENV="${TARIS_DIR}/bot.env"
WRITE_ENV=false

if [[ -f "$BOT_ENV" ]]; then
  warn "bot.env already exists at ${BOT_ENV}"
  if [[ "$YES" == false ]]; then
    ask "Overwrite with new template?" && WRITE_ENV=true
  fi
else
  WRITE_ENV=true
fi

if [[ "$WRITE_ENV" == true ]]; then
  if [[ "$YES" == false ]]; then
    echo ""
    echo "  Enter secrets (leave blank to fill in manually later):"
    BOT_TOKEN=$(prompt "  Telegram BOT_TOKEN")
    ALLOWED_USERS=$(prompt "  ALLOWED_USERS (Telegram chat ID)")
  else
    BOT_TOKEN="<your_telegram_bot_token>"
    ALLOWED_USERS="<your_telegram_chat_id>"
  fi

  PIPER_BIN="${TARIS_DIR}/piper/piper"
  PIPER_MODEL="${TARIS_DIR}/ru_RU-irina-medium.onnx"
  VOSK_PATH="${TARIS_DIR}/vosk-model-small-ru-0.22"

  cat > "$BOT_ENV" << ENVEOF
# bot.env — Taris PicoClaw (Raspberry Pi) — generated by install_picoclaw.sh
# Edit and fill in all <placeholder> values before starting services.

# ── Core — Telegram ───────────────────────────────────────────────────────────
BOT_TOKEN=${BOT_TOKEN}
ALLOWED_USERS=${ALLOWED_USERS}
# ADMIN_USERS=<admin_telegram_chat_id>

# ── Deployment variant ────────────────────────────────────────────────────────
DEVICE_VARIANT=picoclaw

# ── LLM provider ─────────────────────────────────────────────────────────────
LLM_PROVIDER=taris
# LLM_PROVIDER=openai
# OPENAI_API_KEY=sk-...
# OPENAI_MODEL=gpt-4o-mini

# ── Voice — STT ───────────────────────────────────────────────────────────────
STT_PROVIDER=vosk
STT_LANG=ru
VOSK_MODEL_PATH=${VOSK_PATH}

# ── Voice — TTS ───────────────────────────────────────────────────────────────
PIPER_BIN=${PIPER_BIN}
PIPER_MODEL=${PIPER_MODEL}

# ── Storage backend ───────────────────────────────────────────────────────────
STORE_BACKEND=sqlite
# STORE_BACKEND=postgres
# STORE_PG_DSN=postgresql://taris:password@localhost:5432/taris

# ── Web UI ────────────────────────────────────────────────────────────────────
# ROOT_PATH=/taris
# TARIS_API_TOKEN=<strong_random_token>

# ── Embeddings (optional, set to empty to disable on Pi 3 with 1 GB RAM) ────
# EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBED_KEEP_RESIDENT=0

# ── Nextcloud backup (optional) ───────────────────────────────────────────────
# NEXTCLOUD_URL=https://cloud.example.com
# NEXTCLOUD_USER=<username>
# NEXTCLOUD_PASS=<app_password>
# NEXTCLOUD_REMOTE=/TarisBackups
ENVEOF

  chmod 600 "$BOT_ENV"
  chown "${TARIS_USER}:${TARIS_USER}" "$BOT_ENV"
  ok "bot.env written to ${BOT_ENV}"
else
  ok "Existing bot.env preserved"
fi

# ── Step 8: Systemd services ─────────────────────────────────────────────────
hdr "Step 8/9 — Systemd services"
SERVICES=(taris-telegram taris-web taris-voice)

for svc in "${SERVICES[@]}"; do
  SVC_SRC="${SRC_DIR}/services/${svc}.service"
  if [[ -f "$SVC_SRC" ]]; then
    cp "$SVC_SRC" "${SYSTEMD_DIR}/${svc}.service"
    info "  Installed: ${svc}.service"
  else
    warn "  Not found (skip): ${SVC_SRC}"
  fi
done

systemctl daemon-reload

for svc in taris-telegram taris-web; do
  [[ -f "${SYSTEMD_DIR}/${svc}.service" ]] && systemctl enable "$svc" 2>/dev/null || true
done

# Install sqlite-vec extension
SQLITE_VEC_SCRIPT="${SRC_DIR}/setup/install_sqlite_vec.sh"
if [[ -f "$SQLITE_VEC_SCRIPT" ]]; then
  info "Installing sqlite-vec extension..."
  bash "$SQLITE_VEC_SCRIPT" 2>/dev/null || warn "sqlite-vec install had issues — check manually"
fi

ok "Services configured"

# ── Step 9: Cron jobs ────────────────────────────────────────────────────────
hdr "Step 9/9 — Cron jobs"
CRON_JOB="0 19 * * * python3 ${TARIS_DIR}/gmail_digest.py >> ${TARIS_DIR}/digest.log 2>&1"
CURRENT_CRONTAB=$(crontab -u "${TARIS_USER}" -l 2>/dev/null || true)
if echo "${CURRENT_CRONTAB}" | grep -qF "gmail_digest.py"; then
  ok "Gmail digest cron already present"
else
  (echo "${CURRENT_CRONTAB}"; echo "${CRON_JOB}") | crontab -u "${TARIS_USER}" -
  ok "Gmail digest cron installed (19:00 daily)"
fi

# ── Final summary ─────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║              Installation Summary                       ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo "  Install dir : ${TARIS_DIR}"
echo "  Variant     : picoclaw"
echo "  Bot config  : ${BOT_ENV}"
echo ""
BOT_TOKEN_SET=$(grep "BOT_TOKEN=" "$BOT_ENV" 2>/dev/null | grep -v "^#" | grep -v "<" | head -1 || true)
if [[ -z "$BOT_TOKEN_SET" ]]; then
  echo -e "  ${Y}⚠  ACTION REQUIRED: fill in bot.env secrets:${N}"
  echo "     nano ${BOT_ENV}"
  echo ""
fi
echo "  Start services:"
echo "    sudo systemctl start taris-telegram taris-web"
echo ""
echo "  View logs:"
echo "    journalctl -u taris-telegram -f --no-pager"
echo ""
echo "  To update in future (from developer machine):"
echo "    bash src/setup/update_picoclaw.sh --target pi2"
echo ""
