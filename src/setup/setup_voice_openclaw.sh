#!/usr/bin/env bash
# setup_voice_openclaw.sh — Voice pipeline setup for OpenClaw (x86_64 / amd64)
#
# Installs Vosk STT + Piper TTS for Russian voice on Ubuntu/Debian x86_64.
# Mirrors the aarch64 install.sh voice steps but uses x86_64 binaries/models.
#
# Usage (run as normal user, NOT root):
#   bash src/setup/setup_voice_openclaw.sh
#
# Environment:
#   TARIS_HOME — bot data dir (default: ~/.taris)
#   PIPER_VERSION — Piper release tag (default: 1.2.0)
#
# After this script, set in bot.env / environment:
#   VOSK_MODEL_PATH=$TARIS_HOME/vosk-model-small-ru-0.22
#   PIPER_BIN=$TARIS_HOME/piper/piper
#   PIPER_MODEL=$TARIS_HOME/ru_RU-irina-medium.onnx
#   VOICE_BACKEND=cpu      # or cuda if you have NVIDIA GPU + CUDA whisper-cpp

set -euo pipefail

TARIS_HOME="${TARIS_HOME:-$HOME/.taris}"
PIPER_VERSION="${PIPER_VERSION:-1.2.0}"
PIPER_ARCH="x86_64"

# ─── URLs ────────────────────────────────────────────────────────────────────
PIPER_URL="https://github.com/rhasspy/piper/releases/download/${PIPER_VERSION}/piper_linux_${PIPER_ARCH}.tar.gz"
VOSK_MODEL_URL="https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip"
PIPER_VOICE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx"
PIPER_VOICE_CFG_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx.json"

# ─── Helpers ─────────────────────────────────────────────────────────────────
info()  { echo "==> $*"; }
warn()  { echo "[WARN] $*"; }
check() { command -v "$1" &>/dev/null; }

mkdir -p "$TARIS_HOME"

echo "======================================================="
echo " Taris Voice Setup — OpenClaw / x86_64"
echo "======================================================="
echo "  TARIS_HOME  : $TARIS_HOME"
echo "  Piper       : $PIPER_VERSION ($PIPER_ARCH)"
echo ""

# ─── Step 1: System packages ─────────────────────────────────────────────────
info "[1/5] Checking system packages..."
MISSING_PKGS=()
check ffmpeg      || MISSING_PKGS+=(ffmpeg)
check sox         || MISSING_PKGS+=(sox)
python3 -c "import sounddevice" 2>/dev/null || MISSING_PKGS+=(python3-sounddevice)

if [ ${#MISSING_PKGS[@]} -gt 0 ]; then
    info "Installing: ${MISSING_PKGS[*]}"
    if [[ "$(id -u)" -eq 0 ]]; then
        apt-get install -y "${MISSING_PKGS[@]}"
    else
        sudo apt-get install -y "${MISSING_PKGS[@]}"
    fi
fi
info "System packages OK."

# ─── Step 2: Python voice packages ───────────────────────────────────────────
info "[2/5] Installing Python voice packages..."
# On Debian Bookworm (Python 3.12+): --break-system-packages is required.
# On older Debian / venv: the flag is silently ignored.
PIP_FLAGS="--break-system-packages --quiet"
python3 -m pip install $PIP_FLAGS vosk sounddevice webrtcvad scipy
info "vosk, sounddevice, webrtcvad, scipy installed."

# ─── Step 3: Vosk Russian model ──────────────────────────────────────────────
VOSK_DIR="$TARIS_HOME/vosk-model-small-ru-0.22"
if [ -d "$VOSK_DIR" ]; then
    info "[3/5] Vosk model already present at $VOSK_DIR — skipping."
else
    info "[3/5] Downloading Vosk Russian model..."
    TMP_ZIP=$(mktemp /tmp/vosk-model-XXXXXX.zip)
    curl -L --progress-bar "$VOSK_MODEL_URL" -o "$TMP_ZIP"
    info "Extracting to $TARIS_HOME/..."
    unzip -q "$TMP_ZIP" -d "$TARIS_HOME/"
    rm -f "$TMP_ZIP"
    info "Vosk model: $VOSK_DIR"
fi

# ─── Step 4: Piper binary (x86_64) ───────────────────────────────────────────
PIPER_DIR="$TARIS_HOME/piper"
PIPER_BIN="$PIPER_DIR/piper"

if [ -x "$PIPER_BIN" ]; then
    info "[4/5] Piper binary already at $PIPER_BIN — skipping."
else
    info "[4/5] Downloading Piper $PIPER_VERSION for $PIPER_ARCH..."
    TMP_TGZ=$(mktemp /tmp/piper-XXXXXX.tar.gz)
    curl -L --progress-bar "$PIPER_URL" -o "$TMP_TGZ"
    mkdir -p "$PIPER_DIR"
    tar -xzf "$TMP_TGZ" -C "$PIPER_DIR" --strip-components=1
    rm -f "$TMP_TGZ"
    chmod +x "$PIPER_BIN"
    info "Piper binary: $PIPER_BIN"
fi

# Create symlink in /usr/local/bin if writable (optional convenience)
if [ ! -e "/usr/local/bin/piper" ] && [ -w "/usr/local/bin" ]; then
    ln -sf "$PIPER_BIN" /usr/local/bin/piper
    info "Symlinked: /usr/local/bin/piper -> $PIPER_BIN"
fi

# ─── Step 5: Piper Russian voice model ───────────────────────────────────────
ONNX="$TARIS_HOME/ru_RU-irina-medium.onnx"
ONNX_JSON="$TARIS_HOME/ru_RU-irina-medium.onnx.json"

if [ -f "$ONNX" ] && [ -f "$ONNX_JSON" ]; then
    info "[5/6] Piper voice model already present — skipping."
else
    info "[5/6] Downloading Piper Russian voice model..."
    [ -f "$ONNX" ] || curl -L --progress-bar "$PIPER_VOICE_URL"     -o "$ONNX"
    [ -f "$ONNX_JSON" ] || curl -L --progress-bar "$PIPER_VOICE_CFG_URL" -o "$ONNX_JSON"
    info "Piper model: $ONNX"
fi

# ─── Step 6: faster-whisper (recommended STT for OpenClaw/laptop) ─────────────
# faster-whisper uses CTranslate2 for much better WER than Vosk small model.
# small model is recommended for all modern OpenClaw hardware (i5/i7/Ryzen).
# base model (74M) achieves ~25% WER for Russian — insufficient for command use.
# small model (244M) achieves ~5-8% WER and runs comfortably on modern CPUs/APUs.
FASTER_WHISPER_MODEL_NAME="${FASTER_WHISPER_MODEL:-small}"
info "[6/6] Installing faster-whisper (STT for OpenClaw)..."
if python3 -c "import faster_whisper" 2>/dev/null; then
    info "faster-whisper already installed."
else
    python3 -m pip install faster-whisper $PIP_FLAGS
    info "faster-whisper installed."
fi
# Warm up / pre-download model
info "Pre-downloading faster-whisper model: ${FASTER_WHISPER_MODEL_NAME}..."
python3 -c "
from faster_whisper import WhisperModel
import sys
try:
    m = WhisperModel('${FASTER_WHISPER_MODEL_NAME}', device='cpu', compute_type='int8')
    print('[OK] faster-whisper model loaded successfully')
except Exception as e:
    print(f'[WARN] Model pre-download failed: {e}', file=sys.stderr)
    print('      It will download automatically on first use.')
" || true

# ─── Summary ─────────────────────────────────────────────────────────────────
echo ""
echo "======================================================="
echo " Voice pipeline setup complete!"
echo "======================================================="
echo ""
echo "Add to $TARIS_HOME/bot.env:"
echo "  STT_PROVIDER=faster_whisper"
echo "  FASTER_WHISPER_MODEL=${FASTER_WHISPER_MODEL_NAME}"
echo "  FASTER_WHISPER_THREADS=4        # increase for multi-core (8+ for Ryzen/i9)"
echo "  VOSK_MODEL_PATH=$VOSK_DIR"
echo "  PIPER_BIN=$PIPER_BIN"
echo "  PIPER_MODEL=$ONNX"
echo "  VOICE_BACKEND=cpu"
echo ""
echo "STT comparison (modern hardware, CPU-only):"
echo "  faster_whisper small  — WER ~5-8%,  RTF ~0.4-0.8  (recommended default)"
echo "  faster_whisper medium — WER ~3-5%,  RTF ~0.9-1.5  (best accuracy, ~1.5 GB)"
echo "  faster_whisper base   — WER ~20-25%, RTF ~0.2-0.4  (insufficient WER for commands)"
echo "  vosk small-ru         — WER ~15-20%, RTF ~0.1       (Pi-tuned, still works on Pi)"
echo ""
echo "For NVIDIA GPU (faster-whisper):"
echo "  FASTER_WHISPER_DEVICE=cuda"
echo "  FASTER_WHISPER_COMPUTE=float16"
echo ""
echo "For AMD GPU with ROCm (e.g. Radeon 890M on Ryzen AI):"
echo "  FASTER_WHISPER_DEVICE=auto       # CTranslate2 auto-detects ROCm if installed"
echo "  FASTER_WHISPER_COMPUTE=float16   # float16 requires ROCm ≥5.6"
echo "  # Note: CPU int8 is usually faster than ROCm float16 for small/medium models"
echo "  # Benchmark both before switching: set FASTER_WHISPER_DEVICE=cpu for baseline"
echo ""
