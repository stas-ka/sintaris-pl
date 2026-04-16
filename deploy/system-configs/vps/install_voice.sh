#!/usr/bin/env bash
# install_voice.sh — STT + TTS voice stack for Taris on VPS (ARM64/aarch64)
#
# Installs:
#   - ffmpeg (OGG decode/encode, required even without live voice)
#   - faster-whisper (STT for Telegram voice messages)
#   - vosk (optional STT fallback)
#   - Piper TTS binary (aarch64) + Russian voice model
#
# VPS voice mode: Telegram-only (no microphone, no live assistant)
#   - Transcribes incoming OGG voice messages via faster-whisper
#   - Synthesizes voice replies via Piper TTS → OGG (ffmpeg)
#   - Set VOICE_DISABLED=1 in bot.env (disables live voice assistant service)
#
# Benchmarks (VPS ARM Neoverse-N1, 6-core, CPU-only, int8) — measured 2026-04-16:
#   faster-whisper tiny : RTF=0.14 (7× real-time), ~250 MB RAM peak
#   faster-whisper base : RTF=0.23 (4× real-time), ~350 MB RAM peak  ← recommended
#   Piper TTS 139 chars : 1.43s synthesis, 9.7s audio, RTF=0.15
#
# Usage (run as normal user on VPS, NOT root):
#   bash deploy/system-configs/vps/install_voice.sh
#
# Environment variables (optional overrides):
#   TARIS_HOME       — bot data dir (default: ~/.taris)
#   PIPER_VERSION    — piper release tag (default: 2023.11.14-2)
#   WHISPER_MODEL    — model to pre-download: tiny|base|small (default: base)

set -euo pipefail

TARIS_HOME="${TARIS_HOME:-$HOME/.taris}"
PIPER_VERSION="${PIPER_VERSION:-2023.11.14-2}"
PIPER_ARCH="aarch64"
WHISPER_MODEL="${WHISPER_MODEL:-base}"

PIPER_URL="https://github.com/rhasspy/piper/releases/download/${PIPER_VERSION}/piper_linux_${PIPER_ARCH}.tar.gz"
PIPER_RU_ONNX="https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx"
PIPER_RU_JSON="${PIPER_RU_ONNX}.json"
VOSK_RU_MODEL="https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip"

info()  { echo "==> $*"; }
warn()  { echo "[WARN] $*"; }
check() { command -v "$1" &>/dev/null; }

echo "======================================================="
echo " Taris Voice Setup — VPS ARM64/aarch64"
echo "======================================================="
echo "  TARIS_HOME    : $TARIS_HOME"
echo "  Piper         : $PIPER_VERSION ($PIPER_ARCH)"
echo "  Whisper model : $WHISPER_MODEL"
echo ""

mkdir -p "$TARIS_HOME"

# ─── Step 1: System packages ─────────────────────────────────────────────────
info "[1/5] System packages..."
MISSING=()
check ffmpeg  || MISSING+=(ffmpeg)
check unzip   || MISSING+=(unzip)
check curl    || MISSING+=(curl)

if [ ${#MISSING[@]} -gt 0 ]; then
    info "Installing: ${MISSING[*]}"
    sudo apt-get install -y "${MISSING[@]}" -qq
fi
info "ffmpeg: $(ffmpeg -version 2>&1 | head -1 | awk '{print $3}')"

# ─── Step 2: Python packages ─────────────────────────────────────────────────
info "[2/5] Python packages (faster-whisper, vosk)..."
# ARM64 wheels verified: ctranslate2-4.7.1-aarch64, onnxruntime-1.24.4-aarch64, vosk-0.3.45-aarch64
pip3 install --break-system-packages --quiet faster-whisper vosk
info "faster-whisper: $(pip3 show faster-whisper 2>/dev/null | grep Version | awk '{print $2}')"

# ─── Step 3: Piper binary (aarch64) ──────────────────────────────────────────
PIPER_DIR="$TARIS_HOME/piper"
PIPER_BIN="$PIPER_DIR/piper"

if [ -f "$PIPER_BIN" ]; then
    info "[3/5] Piper binary already installed — skipping."
else
    info "[3/5] Downloading Piper aarch64 binary..."
    mkdir -p "$PIPER_DIR"
    TMP_TGZ=$(mktemp /tmp/piper-XXXXXX.tar.gz)
    curl -sL --progress-bar "$PIPER_URL" -o "$TMP_TGZ"
    tar -xzf "$TMP_TGZ" -C "$PIPER_DIR/" --strip-components=1
    chmod +x "$PIPER_BIN"
    rm -f "$TMP_TGZ"
fi
info "Piper: $PIPER_BIN ($(ls -lh $PIPER_BIN | awk '{print $5}'))"

# ─── Step 4: Piper Russian voice model ───────────────────────────────────────
PIPER_MODEL="$TARIS_HOME/ru_RU-irina-medium.onnx"

if [ -f "$PIPER_MODEL" ]; then
    info "[4/5] RU voice model already present — skipping."
else
    info "[4/5] Downloading Russian voice model (Irina, medium)..."
    curl -sL --progress-bar "$PIPER_RU_ONNX" -o "$PIPER_MODEL"
    curl -sL --progress-bar "$PIPER_RU_JSON" -o "${PIPER_MODEL}.json"
fi
MODEL_MB=$(du -m "$PIPER_MODEL" | cut -f1)
info "Voice model: $MODEL_MB MB"

# ─── Step 5: Pre-download Whisper model ──────────────────────────────────────
info "[5/5] Pre-downloading faster-whisper '$WHISPER_MODEL' model..."
python3 - << PYEOF
from faster_whisper import WhisperModel
import os
print(f"Downloading '{os.environ.get('WHISPER_MODEL_NAME', 'base')}' model...")
m = WhisperModel("${WHISPER_MODEL}", device='cpu', compute_type='int8')
print("Model ready.")
del m
PYEOF

# ─── Summary ─────────────────────────────────────────────────────────────────
echo ""
echo "======================================================="
echo " Voice Setup Complete!"
echo "======================================================="
echo ""
echo " Add to ~/.taris/bot.env:"
echo ""
echo "   # STT: local faster-whisper (ARM64, CPU, int8)"
echo "   STT_PROVIDER=faster_whisper"
echo "   FASTER_WHISPER_MODEL=${WHISPER_MODEL}"
echo "   FASTER_WHISPER_DEVICE=cpu"
echo "   FASTER_WHISPER_COMPUTE=int8"
echo "   FASTER_WHISPER_THREADS=4"
echo "   FASTER_WHISPER_PRELOAD=0  # lazy load — saves ~350 MB RAM at idle"
echo ""
echo "   # Or: OpenAI Whisper API (zero RAM, best quality, \$0.006/min)"
echo "   # STT_PROVIDER=openai_whisper"
echo "   # STT_FALLBACK_PROVIDER=faster_whisper"
echo ""
echo "   # TTS: Piper aarch64"
echo "   PIPER_BIN=${PIPER_BIN}"
echo "   PIPER_MODEL=${PIPER_MODEL}"
echo ""
echo "   # Disable live voice assistant (no mic on VPS)"
echo "   VOICE_DISABLED=1"
echo ""
echo " Performance (measured on VPS ARM Neoverse-N1):"
echo "   STT tiny  RTF=0.14 (7x real-time, ~250 MB RAM peak)"
echo "   STT base  RTF=0.23 (4x real-time, ~350 MB RAM peak)"
echo "   TTS 139ch : 1.4s synthesis → 9.7s audio (RTF=0.15)"
