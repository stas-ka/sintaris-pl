#!/usr/bin/env bash
# setup_llm_openclaw.sh — Local LLM (Ollama) setup for OpenClaw variant
#
# Installs Ollama, configures GPU acceleration (AMD/NVIDIA), and pulls a model.
# Supports both CPU-only (TariStation2 / i7) and GPU (SintAItion / Ryzen AI + Radeon 890M).
#
# Usage (run as normal user, NOT root):
#   bash src/setup/setup_llm_openclaw.sh [--model <name>] [--gpu]
#
# Recommended models by hardware:
#   CPU only (i7-2640M, 7.6 GB RAM):
#     qwen2:0.5b  — 512 MB, fastest, good for short answers  (default)
#     llama3.2:1b — 1.3 GB, better quality, ~3-5s/response
#
#   AMD Radeon 890M / 16 GB shared VRAM (SintAItion / Ryzen AI 9):
#     qwen3:14b   — 9.3 GB, excellent quality, ~1-2s/response on GPU  (--gpu default)
#     qwen2:0.5b  — 512 MB, ultra-fast baseline
#
# GPU requirements (AMD iGPU):
#   - amdgpu kernel module loaded  (check: lsmod | grep amdgpu)
#   - /dev/kfd present             (check: ls /dev/kfd)
#   - User in render+video groups  (auto-configured by --gpu flag)
#   - Ollama system service        (auto-created by --gpu flag)
#
# After install, set in ~/.taris/bot.env:
#   LLM_PROVIDER=ollama
#   OLLAMA_MODEL=qwen2:0.5b   # or qwen3:14b for GPU
#   LLM_LOCAL_FALLBACK=1

set -euo pipefail

OLLAMA_MODEL=""
GPU_MODE=0

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --model) OLLAMA_MODEL="$2"; shift 2 ;;
        --gpu)   GPU_MODE=1; shift ;;
        -h|--help)
            echo "Usage: $0 [--model <name>] [--gpu]"
            echo "  --model  Ollama model to pull (default: qwen2:0.5b, or qwen3:14b with --gpu)"
            echo "  --gpu    Configure AMD GPU acceleration (requires sudo)"
            exit 0 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Default model depends on GPU mode
if [[ -z "$OLLAMA_MODEL" ]]; then
    if [[ "$GPU_MODE" -eq 1 ]]; then
        OLLAMA_MODEL="qwen3:14b"
    else
        OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2:0.5b}"
    fi
fi

info()  { echo "==> $*"; }
ok()    { echo "    ✓ $*"; }
warn()  { echo "[WARN] $*"; }

echo "======================================================="
echo " Taris LLM Setup — OpenClaw / Ollama"
echo "======================================================="
echo "  Model:    $OLLAMA_MODEL"
echo "  GPU mode: $([ $GPU_MODE -eq 1 ] && echo 'AMD ROCm' || echo 'CPU only')"
echo ""

# ─── Step 1: Install Ollama ───────────────────────────────────────────────────
if command -v ollama &>/dev/null; then
    ok "Ollama already installed: $(ollama --version 2>/dev/null || echo 'unknown version')"
else
    info "[1/4] Installing Ollama..."
    curl -fsSL https://ollama.ai/install.sh | sh
    ok "Ollama installed."
fi

# ─── Step 2: Configure Ollama service ────────────────────────────────────────
info "[2/4] Configuring Ollama service..."

if [[ "$GPU_MODE" -eq 1 ]]; then
    # ── AMD GPU setup ──────────────────────────────────────────────────────────
    # Detect GPU (gfx version from KFD topology)
    GFX_VER=$(cat /sys/devices/virtual/kfd/kfd/topology/nodes/*/properties 2>/dev/null \
              | grep gfx_target_version | awk '{print $2}' | head -1)
    if [[ -z "$GFX_VER" ]]; then
        warn "No AMD GPU KFD device found. Is amdgpu loaded? (lsmod | grep amdgpu)"
        warn "Falling back to CPU mode."
        GPU_MODE=0
    else
        # Convert 110500 → 11.0.3 override (use gfx1103 for Strix Point gfx1105)
        MAJOR=$(( GFX_VER / 10000 ))
        MINOR=$(( (GFX_VER % 10000) / 100 ))
        # gfx1105 (Strix Point) → override to gfx1103 (Phoenix, known-good in ROCm)
        if [[ "$GFX_VER" -ge 110400 ]] && [[ "$GFX_VER" -lt 110600 ]]; then
            HSA_OVERRIDE="11.0.3"
        else
            HSA_OVERRIDE="${MAJOR}.0.$(( MINOR > 0 ? MINOR - 1 : 0 ))"
        fi
        ok "Detected AMD GPU gfx_target_version=$GFX_VER → HSA_OVERRIDE=${HSA_OVERRIDE}"

        # Add user to render+video groups
        if ! groups | grep -qw render; then
            info "  Adding $(whoami) to render+video groups (requires sudo)..."
            sudo usermod -aG render,video "$(whoami)"
            ok "Groups added. Changes take effect on next login (service uses SupplementaryGroups)."
        else
            ok "User already in render group."
        fi

        # Create system Ollama service with GPU env
        SERVICE_FILE=/etc/systemd/system/ollama.service
        info "  Creating GPU-accelerated system service at $SERVICE_FILE..."
        sudo tee "$SERVICE_FILE" > /dev/null << SVCEOF
[Unit]
Description=Ollama AI LLM Server (GPU-accelerated AMD Radeon)
After=network.target

[Service]
User=$(whoami)
Group=render
SupplementaryGroups=video render
Environment=HOME=$HOME
Environment=OLLAMA_HOST=127.0.0.1:11434
Environment=HSA_OVERRIDE_GFX_VERSION=${HSA_OVERRIDE}
Environment=OLLAMA_FLASH_ATTENTION=1
Environment=OLLAMA_KEEP_ALIVE=1h
Environment=LD_LIBRARY_PATH=/usr/local/lib/ollama/rocm
ExecStart=/usr/local/bin/ollama serve
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVCEOF
        sudo systemctl daemon-reload
        sudo systemctl enable --now ollama
        ok "GPU-accelerated system service started."
    fi
fi

if [[ "$GPU_MODE" -eq 0 ]]; then
    # ── CPU-only service ──────────────────────────────────────────────────────
    if systemctl --user is-active ollama &>/dev/null 2>&1; then
        ok "Ollama user service already running."
    elif systemctl is-active ollama &>/dev/null 2>&1; then
        ok "Ollama system service running."
    else
        systemctl --user enable --now ollama 2>/dev/null || \
        systemctl enable --now ollama 2>/dev/null || \
        (ollama serve &>/tmp/ollama.log & sleep 2 && ok "Ollama started in background")
    fi
fi

# Wait for Ollama API
for i in $(seq 1 15); do
    if curl -s http://127.0.0.1:11434/api/tags &>/dev/null; then
        ok "Ollama API is ready."
        break
    fi
    echo "  Waiting for Ollama to start... ($i/15)"
    sleep 2
done

# ─── Step 3: Pull model ──────────────────────────────────────────────────────
info "[3/4] Pulling model: $OLLAMA_MODEL ..."
ollama pull "$OLLAMA_MODEL"
ok "Model $OLLAMA_MODEL ready."

# ─── Step 4: Test ────────────────────────────────────────────────────────────
info "[4/4] Quick inference test..."
RESPONSE=$(curl -s http://127.0.0.1:11434/api/chat \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"$OLLAMA_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with exactly: OK\"}],\"think\":false,\"stream\":false}" \
    2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['message']['content'].strip())" 2>/dev/null || echo "")

if [[ -n "$RESPONSE" ]]; then
    ok "Test response: $RESPONSE"
else
    warn "Test failed — Ollama may still be loading. Try again in 10s."
fi

# ─── Check GPU offload ───────────────────────────────────────────────────────
if [[ "$GPU_MODE" -eq 1 ]]; then
    GPU_LAYERS=$(journalctl -u ollama -n 20 --no-pager 2>/dev/null \
                 | grep "offloaded.*layers to GPU" | tail -1)
    if [[ -n "$GPU_LAYERS" ]]; then
        ok "GPU: $GPU_LAYERS"
    else
        warn "Could not confirm GPU offload — check: journalctl -u ollama -n 30"
    fi
fi

echo ""
echo "======================================================="
echo " Setup complete!"
echo "======================================================="
echo ""
echo "  Set in ~/.taris/bot.env:"
echo "    LLM_PROVIDER=ollama"
echo "    OLLAMA_MODEL=$OLLAMA_MODEL"
if [[ "$GPU_MODE" -eq 1 ]]; then
echo "    OLLAMA_MIN_TIMEOUT=90          # GPU cold-start safety margin"
fi
echo "    LLM_LOCAL_FALLBACK=1"
echo ""
if [[ "$GPU_MODE" -eq 1 ]]; then
echo "  GPU info:"
echo "    Model in VRAM: stays loaded 1h (OLLAMA_KEEP_ALIVE=1h)"
echo "    First query after service restart loads model (~5-10s one-time)"
echo ""
fi
echo "  Test directly:"
echo "    ollama run $OLLAMA_MODEL 'Hello, how are you?'"
echo ""
