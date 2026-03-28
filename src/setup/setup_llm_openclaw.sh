#!/usr/bin/env bash
# setup_llm_openclaw.sh — Local LLM (Ollama) setup for OpenClaw variant
#
# Installs Ollama and pulls a small model for offline LLM on laptop/PC.
# No GPU required — uses CPU inference (i7/i5 2+ cores, 4+ GB RAM).
#
# Usage (run as normal user, NOT root):
#   bash src/setup/setup_llm_openclaw.sh [--model <name>]
#
# Recommended models for i7-2640M (4 cores, 7.6 GB RAM, no GPU):
#   qwen2:0.5b  — 512 MB, fastest, good for short answers  (default)
#   llama3.2:1b — 1.3 GB, better quality, ~3-5s/response
#   phi3:mini   — 2.3 GB, good reasoning, ~5-10s/response
#   mistral:7b  — 4.1 GB, best quality, ~15-30s/response (requires ≥8GB RAM)
#
# After install, set in ~/.taris/bot.env:
#   LLM_PROVIDER=ollama
#   OLLAMA_MODEL=qwen2:0.5b
#   LLM_LOCAL_FALLBACK=1

set -euo pipefail

OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2:0.5b}"

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --model) OLLAMA_MODEL="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 [--model <name>]"
            echo "Models: qwen2:0.5b (default), llama3.2:1b, phi3:mini, mistral:7b"
            exit 0 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

info()  { echo "==> $*"; }
ok()    { echo "    ✓ $*"; }
warn()  { echo "[WARN] $*"; }

echo "======================================================="
echo " Taris LLM Setup — OpenClaw / Ollama"
echo "======================================================="
echo "  Model: $OLLAMA_MODEL"
echo ""

# ─── Step 1: Install Ollama ───────────────────────────────────────────────────
if command -v ollama &>/dev/null; then
    ok "Ollama already installed: $(ollama --version 2>/dev/null || echo 'unknown version')"
else
    info "[1/3] Installing Ollama..."
    curl -fsSL https://ollama.ai/install.sh | sh
    ok "Ollama installed."
fi

# ─── Step 2: Start Ollama service ────────────────────────────────────────────
info "[2/3] Starting Ollama service..."
if systemctl --user is-active ollama &>/dev/null 2>&1; then
    ok "Ollama service already running."
elif systemctl is-active ollama &>/dev/null 2>&1; then
    ok "Ollama system service running."
else
    # Try to start as user service
    systemctl --user enable --now ollama 2>/dev/null || \
    systemctl enable --now ollama 2>/dev/null || \
    (ollama serve &>/tmp/ollama.log & sleep 2 && ok "Ollama started in background (PID: $!)")
fi

# Wait for Ollama to be ready
for i in $(seq 1 10); do
    if curl -s http://127.0.0.1:11434/api/tags &>/dev/null; then
        ok "Ollama API is ready."
        break
    fi
    echo "  Waiting for Ollama to start... ($i/10)"
    sleep 2
done

# ─── Step 3: Pull model ──────────────────────────────────────────────────────
info "[3/3] Pulling model: $OLLAMA_MODEL ..."
ollama pull "$OLLAMA_MODEL"
ok "Model $OLLAMA_MODEL ready."

# ─── Quick test ──────────────────────────────────────────────────────────────
echo ""
info "Quick inference test..."
RESPONSE=$(curl -s http://127.0.0.1:11434/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"$OLLAMA_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with exactly: OK\"}],\"max_tokens\":10}" \
    2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['choices'][0]['message']['content'].strip())" 2>/dev/null || echo "")

if [[ -n "$RESPONSE" ]]; then
    ok "Test response: $RESPONSE"
else
    warn "Test failed — Ollama may still be loading. Try again in 10s."
fi

echo ""
echo "======================================================="
echo " Setup complete!"
echo "======================================================="
echo ""
echo "  To use Ollama as LLM, set in ~/.taris/bot.env:"
echo "    LLM_PROVIDER=ollama"
echo "    OLLAMA_MODEL=$OLLAMA_MODEL"
echo "    LLM_LOCAL_FALLBACK=1"
echo ""
echo "  Or to use as cloud fallback only (keep cloud primary):"
echo "    LLM_PROVIDER=openai        # keep cloud primary"
echo "    LLM_LOCAL_FALLBACK=1       # ollama as fallback"
echo "    LLAMA_CPP_URL=http://127.0.0.1:11434"
echo ""
echo "  Test Ollama directly:"
echo "    ollama run $OLLAMA_MODEL 'Hello, how are you?'"
echo ""
