#!/bin/bash
# =============================================================================
# Picoclaw Russian Voice Assistant — Installation Script
# =============================================================================
# Installs:
#   1. Vosk STT + vosk-model-small-ru (48MB) — offline Russian speech recognition
#   2. Piper TTS + ru_RU-ruslan-medium (66MB ONNX) — offline Russian TTS on Pi 3
#   3. sounddevice + libportaudio2 — audio capture
#   4. RB-TalkingPI I2S driver setup (Joy-IT / Google AIY HAT)
#   5. picoclaw-voice.service systemd unit
#
# Based on KIM-ASSISTANT analysis:
#   - KIM uses Silero/PyTorch TTS (requires ~2GB RAM, unusable on Pi 3)
#   - KIM uses Vosk STT with Russian model — we reuse this approach
#   - Piper TTS replaces Silero: ONNX-based, ~50MB, runs in 1-3s per sentence
#
# Usage:
#   bash /tmp/setup_voice.sh
# =============================================================================

set -e

PICOCLAW_DIR="/home/stas/.picoclaw"
PIPER_VERSION="2.0.0"
PIPER_ARCH="aarch64"
VOSK_MODEL_URL="https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip"
PIPER_URL="https://github.com/rhasspy/piper/releases/download/v${PIPER_VERSION}/piper_${PIPER_ARCH}.tar.gz"
# Russian female voice (Irina — natural, medium quality, ~66MB onnx)
PIPER_VOICE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx"
PIPER_VOICE_JSON_URL="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx.json"

echo "=============================================="
echo " Picoclaw Voice Assistant Setup"
echo " Target: Raspberry Pi 3 B+ (aarch64)"
echo " TTS: Piper + ru_RU-irina-medium"
echo " STT: Vosk + vosk-model-small-ru-0.22"
echo "=============================================="

# ------------------------------------------------------------------------------
# 1. System dependencies
# ------------------------------------------------------------------------------
echo ""
echo "[1/6] Installing system dependencies..."
apt-get update -qq
apt-get install -y --no-install-recommends \
    portaudio19-dev \
    espeak-ng \
    libsndfile1 \
    alsa-utils \
    python3-pip \
    wget \
    unzip \
    tar

# ------------------------------------------------------------------------------
# 2. Python packages (Vosk + sounddevice)
#    From KIM analysis: vosk + sounddevice = proven combo for Pi Russian STT
# ------------------------------------------------------------------------------
echo ""
echo "[2/6] Installing Python packages (vosk + sounddevice)..."
pip3 install --break-system-packages --quiet \
    vosk \
    sounddevice \
    numpy

# ------------------------------------------------------------------------------
# 3. Vosk Russian model (small, 48MB — real-time on Pi 3)
#    KIM uses vosk-model-ru-0.42 (full, 1.5GB) — too large for Pi 3
#    vosk-model-small-ru-0.22 = 48MB, good accuracy for commands
# ------------------------------------------------------------------------------
echo ""
echo "[3/6] Downloading Vosk Russian model (48MB)..."
if [ ! -d "${PICOCLAW_DIR}/vosk-model-small-ru" ]; then
    cd "${PICOCLAW_DIR}"
    wget -q --show-progress "${VOSK_MODEL_URL}" -O vosk-model-small-ru.zip
    unzip -q vosk-model-small-ru.zip
    # Rename extracted dir to consistent name
    extracted=$(ls -d vosk-model-small-ru-* 2>/dev/null | head -1)
    if [ -n "$extracted" ]; then
        mv "$extracted" vosk-model-small-ru
    fi
    rm -f vosk-model-small-ru.zip
    echo "  Vosk model installed: ${PICOCLAW_DIR}/vosk-model-small-ru"
else
    echo "  Vosk model already exists, skipping."
fi

# ------------------------------------------------------------------------------
# 4. Piper TTS (replaces Silero/PyTorch — too heavy for Pi 3 1GB RAM)
#    Piper: ONNX Runtime, ~50MB binary, purpose-built for Pi
# ------------------------------------------------------------------------------
echo ""
echo "[4/6] Installing Piper TTS..."
if [ ! -f "/usr/local/bin/piper" ]; then
    cd /tmp
    # Note: PIPER_URL should be .../piper_linux_aarch64.tar.gz (not piper_aarch64.tar.gz)
    PIPER_URL="https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_aarch64.tar.gz"
    wget -q --show-progress "${PIPER_URL}" -O piper.tar.gz
    tar -xzf piper.tar.gz
    # Install full piper directory (binary + bundled libs: libpiper_phonemize, libonnxruntime, etc.)
    cp -r /tmp/piper /usr/local/share/piper
    # Create wrapper script with LD_LIBRARY_PATH so piper finds its bundled libs
    cat > /usr/local/bin/piper << 'WRAPPER'
#!/bin/sh
export LD_LIBRARY_PATH=/usr/local/share/piper
exec /usr/local/share/piper/piper "$@"
WRAPPER
    chmod +x /usr/local/bin/piper
    rm -rf /tmp/piper /tmp/piper.tar.gz
    echo "  Piper installed: /usr/local/bin/piper (wrapper)"
    echo "  Piper libs: /usr/local/share/piper/"
else
    echo "  Piper already installed, skipping."
fi

echo ""
echo "[4b/6] Downloading Piper Russian voice (Irina, medium, ~66MB)..."
if [ ! -f "${PICOCLAW_DIR}/ru_RU-irina-medium.onnx" ]; then
    cd "${PICOCLAW_DIR}"
    wget -q --show-progress "${PIPER_VOICE_URL}" -O ru_RU-irina-medium.onnx
    wget -q "${PIPER_VOICE_JSON_URL}" -O ru_RU-irina-medium.onnx.json
    echo "  Piper Russian voice installed: ${PICOCLAW_DIR}/ru_RU-irina-medium.onnx"
else
    echo "  Piper Russian voice already exists, skipping."
fi

# Update symlink so voice_assistant.py default path resolves correctly
ln -sf "${PICOCLAW_DIR}/ru_RU-irina-medium.onnx" "${PICOCLAW_DIR}/ru_RU-ruslan-medium.onnx" 2>/dev/null || true

# ------------------------------------------------------------------------------
# 5. RB-TalkingPI (Joy-IT) I2S audio driver setup
#    The RB-TalkingPI uses I2S (Google AIY Voice HAT compatible)
#    We add the googlevoicehat-soundcard dtoverlay to /boot/firmware/config.txt
# ------------------------------------------------------------------------------
echo ""
echo "[5/6] Configuring RB-TalkingPI I2S audio driver..."

CONFIG_FILE="/boot/firmware/config.txt"
# Older Pi OS uses /boot/config.txt
[ -f "$CONFIG_FILE" ] || CONFIG_FILE="/boot/config.txt"

if ! grep -q "googlevoicehat-soundcard" "$CONFIG_FILE" 2>/dev/null; then
    cat >> "$CONFIG_FILE" << 'EOF'

# RB-TalkingPI (Joy-IT) / Google AIY Voice HAT - I2S microphone + amp
dtparam=i2s=on
dtoverlay=googlevoicehat-soundcard
EOF
    echo "  I2S overlay added to ${CONFIG_FILE}"
    echo "  ⚠  REBOOT REQUIRED for audio driver to take effect"
else
    echo "  I2S overlay already configured, skipping."
fi

# Create ALSA config to set the Voice HAT as default audio device
ASOUND_FILE="/home/stas/.asoundrc"
if [ ! -f "$ASOUND_FILE" ]; then
    cat > "$ASOUND_FILE" << 'EOF'
# RB-TalkingPI default ALSA config
# Use card 1 (googlevoicehat) for both playback and capture
pcm.!default {
    type asym
    playback.pcm {
        type plug
        slave.pcm "hw:1,0"
    }
    capture.pcm {
        type plug
        slave.pcm "hw:1,0"
    }
}
ctl.!default {
    type hw
    card 1
}
EOF
    chown stas:stas "$ASOUND_FILE"
    echo "  ALSA config written: ${ASOUND_FILE}"
else
    echo "  ALSA config already exists, skipping."
fi

# ------------------------------------------------------------------------------
# 6. Deploy voice_assistant.py + systemd service
# ------------------------------------------------------------------------------
echo ""
echo "[6/6] Installing voice assistant service..."

# voice_assistant.py should already be at PICOCLAW_DIR from pscp
# If not, we create a minimal placeholder
if [ ! -f "${PICOCLAW_DIR}/voice_assistant.py" ]; then
    echo "  ⚠  voice_assistant.py not found in ${PICOCLAW_DIR}"
    echo "     Copy it first: pscp .credentials/voice_assistant.py stas@OpenClawPI:${PICOCLAW_DIR}/voice_assistant.py"
fi

cat > /etc/systemd/system/picoclaw-voice.service << 'EOF'
[Unit]
Description=Picoclaw Russian Voice Assistant
Documentation=https://github.com/sipeed/picoclaw
After=network.target sound.target picoclaw-gateway.service
Wants=picoclaw-gateway.service

[Service]
Type=simple
User=stas
WorkingDirectory=/home/stas/.picoclaw
ExecStart=/usr/bin/python3 /home/stas/.picoclaw/voice_assistant.py
Restart=on-failure
RestartSec=5
StandardOutput=append:/home/stas/.picoclaw/voice.log
StandardError=append:/home/stas/.picoclaw/voice.log
Environment=PYTHONUNBUFFERED=1
Environment=VOSK_MODEL_PATH=/home/stas/.picoclaw/vosk-model-small-ru
Environment=PIPER_BIN=/usr/local/bin/piper
Environment=PIPER_MODEL=/home/stas/.picoclaw/ru_RU-irina-medium.onnx
Environment=PICOCLAW_BIN=/usr/bin/picoclaw

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable picoclaw-voice.service
echo "  Service installed and enabled."

# ------------------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------------------
echo ""
echo "=============================================="
echo " Setup complete!"
echo "=============================================="
echo ""
echo " Components installed:"
echo "   STT  : Vosk + vosk-model-small-ru (offline Russian)"
echo "   TTS  : Piper + ru_RU-irina-medium.onnx (offline Russian)"
echo "   Audio: RB-TalkingPI I2S dtoverlay configured"
echo ""
echo " IMPORTANT: Reboot is required for I2S to activate:"
echo "   sudo reboot"
echo ""
echo " After reboot, verify audio:"
echo "   arecord -l                  # should show googlevoicehat card"
echo "   aplay -l                    # should show googlevoicehat card"
echo "   arecord -D hw:1,0 -f S16_LE -r 16000 -c 1 test.wav  # test mic"
echo "   aplay test.wav              # play back"
echo ""
echo " Start voice assistant:"
echo "   sudo systemctl start picoclaw-voice"
echo "   journalctl -u picoclaw-voice -f --no-pager"
echo ""
echo " Test Piper TTS manually:"
echo "   echo 'Привет, я Пико!' | piper --model ~/.picoclaw/ru_RU-irina-medium.onnx --output-raw | aplay -r22050 -fS16_LE -c1 -"
echo ""
