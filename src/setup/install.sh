#!/bin/bash
# =============================================================================
# install.sh — Full Fresh-Install Bootstrap  (§6.3.2)
# =============================================================================
# Bootstraps a bare Raspberry Pi OS (Bookworm, aarch64) into a fully working
# Taris Bot installation: taris binary, Telegram bot, Gmail digest, voice
# assistant (RB-TalkingPI), and all systemd services.
#
# Run ONCE on a freshly imaged Pi:
#   sudo bash install.sh
#
# Prerequisites:
#   - Pi connected to internet
#   - User "stas" exists (or adjust TARIS_USER below)
#   - SSH access enabled
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration — edit to match your environment
# ---------------------------------------------------------------------------
TARIS_USER="stas"
TARIS_DIR="/home/${TARIS_USER}/.taris"
SYSTEMD_DIR="/etc/systemd/system"
PIPER_VERSION="1.2.0"
PIPER_ARCH="aarch64"
PIPER_RELEASE_URL="https://github.com/rhasspy/piper/releases/download/${PIPER_VERSION}/piper_linux_${PIPER_ARCH}.tar.gz"
VOSK_MODEL_URL="https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip"
PIPER_VOICE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx"
PICOCLAW_DEB_URL="https://github.com/sipeed/picoclaw/releases/latest/download/picoclaw_aarch64.deb"

# ---------------------------------------------------------------------------

echo "=============================================="
echo " Taris Bot — Full Install Bootstrap"
echo "=============================================="
echo "  Pi user    : ${TARIS_USER}"
echo "  Taris   : ${TARIS_DIR}"
echo ""

if [[ "$(id -u)" -ne 0 ]]; then
  echo "[!] Run as root: sudo bash $0"
  exit 1
fi

# ---------------------------------------------------------------------------
# Step 1 — System packages
# ---------------------------------------------------------------------------
echo "[1/9] Installing system packages..."
apt-get update -qq
apt-get install -y \
  git curl wget python3 python3-pip \
  ffmpeg portaudio19-dev espeak-ng \
  zstd unzip \
  cron

echo "  System packages installed."

# ---------------------------------------------------------------------------
# Step 2 — Python packages
# ---------------------------------------------------------------------------
echo ""
echo "[2/9] Installing Python packages..."
pip3 install --break-system-packages --quiet \
  pyTelegramBotAPI \
  vosk \
  sounddevice \
  google-api-python-client \
  google-auth-httplib2 \
  google-auth-oauthlib \
  requests \
  sqlite-vec

echo "  Python packages installed."

# ---------------------------------------------------------------------------
# Step 3 — taris Go binary
# ---------------------------------------------------------------------------
echo ""
echo "[3/9] Installing taris binary..."
wget -q "${TARIS_DEB_URL}" -O /tmp/taris_aarch64.deb
dpkg -i /tmp/taris_aarch64.deb
rm /tmp/taris_aarch64.deb
taris version
echo "  taris installed."

# ---------------------------------------------------------------------------
# Step 4 — Piper TTS
# ---------------------------------------------------------------------------
echo ""
echo "[4/9] Installing Piper TTS..."
PIPER_SHARE="/usr/local/share/piper"
mkdir -p "${PIPER_SHARE}"
wget -q "${PIPER_RELEASE_URL}" -O /tmp/piper.tar.gz
tar -xzf /tmp/piper.tar.gz -C "${PIPER_SHARE}" --strip-components=1
rm /tmp/piper.tar.gz

# Wrapper script
cat > /usr/local/bin/piper << 'PIPERWRAPPER'
#!/bin/bash
exec /usr/local/share/piper/piper "$@"
PIPERWRAPPER
chmod +x /usr/local/bin/piper
echo "  Piper TTS installed."

# ---------------------------------------------------------------------------
# Step 5 — Taris working directory + models
# ---------------------------------------------------------------------------
echo ""
echo "[5/9] Creating taris directory and downloading models..."
mkdir -p "${TARIS_DIR}"
chown "${TARIS_USER}:${TARIS_USER}" "${TARIS_DIR}"

# Vosk Russian model
if [[ ! -d "${TARIS_DIR}/vosk-model-small-ru" ]]; then
  wget -q "${VOSK_MODEL_URL}" -O /tmp/vosk-model.zip
  unzip -q /tmp/vosk-model.zip -d "${TARIS_DIR}/"
  mv "${TARIS_DIR}/vosk-model-small-ru-0.22" "${TARIS_DIR}/vosk-model-small-ru" 2>/dev/null || true
  rm /tmp/vosk-model.zip
  echo "  Vosk model downloaded."
else
  echo "  Vosk model already present."
fi

# Piper Russian voice (Irina medium)
if [[ ! -f "${TARIS_DIR}/ru_RU-irina-medium.onnx" ]]; then
  wget -q "${PIPER_VOICE_URL}" -O "${TARIS_DIR}/ru_RU-irina-medium.onnx"
  # .onnx.json metadata
  wget -q "${PIPER_VOICE_URL}.json" -O "${TARIS_DIR}/ru_RU-irina-medium.onnx.json" 2>/dev/null || true
  echo "  Piper voice model downloaded."
else
  echo "  Piper voice model already present."
fi

chown -R "${TARIS_USER}:${TARIS_USER}" "${TARIS_DIR}"

# ---------------------------------------------------------------------------
# Step 6 — taris onboard (initialize config)
# ---------------------------------------------------------------------------
echo ""
echo "[6/9] Initialising taris workspace..."
if [[ ! -f "${TARIS_DIR}/config.json" ]]; then
  sudo -u "${TARIS_USER}" taris onboard || true
  echo "  taris workspace initialised."
else
  echo "  config.json already exists, skipping onboard."
fi

# ---------------------------------------------------------------------------
# Step 7 — Deploy bot source files
# ---------------------------------------------------------------------------
echo ""
echo "[7/9] Deploying bot source files..."
SCRIPT_DIR="$(dirname "$(realpath "${BASH_SOURCE[0]}")")"
SRC_DIR="$(realpath "${SCRIPT_DIR}/..")"

for f in telegram_menu_bot.py gmail_digest.py voice_assistant.py \
          strings.json release_notes.json; do
  if [[ -f "${SRC_DIR}/${f}" ]]; then
    cp "${SRC_DIR}/${f}" "${TARIS_DIR}/${f}"
    echo "  Deployed: ${f}"
  else
    echo "  [!] Not found (skip): ${SRC_DIR}/${f}"
  fi
done

# bot.env — copy template if secrets file not present
BOT_ENV_TEMPLATE="${SRC_DIR}/setup/bot.env.example"
if [[ ! -f "${TARIS_DIR}/bot.env" ]] && [[ -f "${BOT_ENV_TEMPLATE}" ]]; then
  cp "${BOT_ENV_TEMPLATE}" "${TARIS_DIR}/bot.env"
  echo "  bot.env created from template — fill in secrets before starting services!"
fi

chown -R "${TARIS_USER}:${TARIS_USER}" "${TARIS_DIR}"

# ---------------------------------------------------------------------------
# Step 8 — Install systemd service units
# ---------------------------------------------------------------------------
echo ""
echo "[8/9] Installing systemd services..."
SERVICES_DIR="${SRC_DIR}/services"
SERVICES=(taris-gateway taris-telegram taris-voice)

for svc in "${SERVICES[@]}"; do
  SVC_FILE="${SERVICES_DIR}/${svc}.service"
  if [[ -f "${SVC_FILE}" ]]; then
    cp "${SVC_FILE}" "${SYSTEMD_DIR}/${svc}.service"
    echo "  Installed: ${svc}.service"
  else
    echo "  [!] Service file not found (skip): ${SVC_FILE}"
  fi
done

systemctl daemon-reload

for svc in "${SERVICES[@]}"; do
  if [[ -f "${SYSTEMD_DIR}/${svc}.service" ]]; then
    systemctl enable "${svc}" || true
    echo "  Enabled: ${svc}"
  fi
done

# ---------------------------------------------------------------------------
# Step 9 — Cron jobs
# ---------------------------------------------------------------------------
echo ""
echo "[9/9] Installing cron jobs..."
CRON_JOB="0 19 * * * python3 ${TARIS_DIR}/gmail_digest.py >> ${TARIS_DIR}/digest.log 2>&1"
CURRENT_CRONTAB=$(sudo -u "${TARIS_USER}" crontab -l 2>/dev/null || true)
if echo "${CURRENT_CRONTAB}" | grep -qF "gmail_digest.py"; then
  echo "  Gmail digest cron already present."
else
  (echo "${CURRENT_CRONTAB}"; echo "${CRON_JOB}") | sudo -u "${TARIS_USER}" crontab -
  echo "  Gmail digest cron installed (19:00 daily)."
fi

# ---------------------------------------------------------------------------
echo ""
echo "=============================================="
echo " Installation complete."
echo "=============================================="
echo ""
echo " Next steps:"
echo "  1. Fill in secrets: ${TARIS_DIR}/bot.env"
echo "     Required: BOT_TOKEN, ALLOWED_USER, ADMIN_USERS, OPENROUTER_API_KEY"
echo ""
echo "  2. Fill in taris config: ${TARIS_DIR}/config.json"
echo "     Required: model_list with API key"
echo ""
echo "  3. (Voice) Physically attach RB-TalkingPI HAT and reboot:"
echo "     sudo reboot"
echo ""
echo "  4. Start services:"
echo "     sudo systemctl start taris-telegram"
echo "     sudo systemctl start taris-gateway"
echo "     sudo systemctl start taris-voice   # after reboot with RB-TalkingPI"
