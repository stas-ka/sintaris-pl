#!/usr/bin/env bash
# run_gemma4_evaluation.sh — Gemma4 LLM evaluation on Linux targets (TariStation2 / SintAItion)
#
# Usage:
#   bash run_gemma4_evaluation.sh [TARGET_LABEL]
#
# Examples:
#   bash run_gemma4_evaluation.sh TariStation2
#   bash run_gemma4_evaluation.sh SintAItion
#
# The script:
#   1. Checks Ollama is running
#   2. Pulls gemma4:e2b and gemma4:e4b (skips if already present)
#   3. Runs the benchmark against current model + both gemma4 variants
#   4. Saves results to ~/.taris/tests/gemma4_eval_<timestamp>.json
#   5. Prints a comparison table
#
# Prerequisites on the target machine:
#   - ollama installed and running (`systemctl --user status ollama`)
#   - python3 available
#   - Project source at ~/projects/sintaris-pl (or TARIS_SRC env var)
set -euo pipefail

TARGET="${1:-$(hostname)}"
TARIS_SRC="${TARIS_SRC:-$HOME/projects/sintaris-pl}"
BENCH="$TARIS_SRC/src/tests/llm/benchmark_ollama_models.py"
RESULTS_DIR="${HOME}/.taris/tests"
TS=$(date -u +%Y%m%d_%H%M)
SAVE_PATH="$RESULTS_DIR/gemma4_eval_${TS}.json"
OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"

# ── helpers ────────────────────────────────────────────────────────────────────
info()  { echo -e "\033[1;32m[INFO]\033[0m  $*"; }
warn()  { echo -e "\033[1;33m[WARN]\033[0m  $*"; }
error() { echo -e "\033[1;31m[ERROR]\033[0m $*" >&2; }

# ── pre-flight ─────────────────────────────────────────────────────────────────
info "Gemma4 Evaluation — target: $TARGET — $(date -u +'%Y-%m-%d %H:%M UTC')"

if ! curl -sf "$OLLAMA_URL/api/tags" >/dev/null; then
    error "Ollama is not running at $OLLAMA_URL"
    error "Start it: systemctl --user start ollama"
    exit 1
fi
info "Ollama reachable at $OLLAMA_URL"

if [ ! -f "$BENCH" ]; then
    error "Benchmark script not found: $BENCH"
    error "Set TARIS_SRC to the project root, e.g.:  TARIS_SRC=~/projects/sintaris-pl $0"
    exit 1
fi

mkdir -p "$RESULTS_DIR"

# ── pull models ────────────────────────────────────────────────────────────────
MODELS_TO_PULL=("gemma4:e2b" "gemma4:e4b")
MODELS_PULLED=()

EXISTING=$(curl -sf "$OLLAMA_URL/api/tags" | python3 -c "import sys,json; [print(m['name']) for m in json.load(sys.stdin).get('models',[])]" 2>/dev/null || true)

for MODEL in "${MODELS_TO_PULL[@]}"; do
    BASE="${MODEL%%:*}"
    TAG="${MODEL##*:}"
    if echo "$EXISTING" | grep -q "$BASE.*$TAG"; then
        info "Model $MODEL already present — skipping pull"
    else
        info "Pulling $MODEL (this may take a few minutes) ..."
        ollama pull "$MODEL"
        info "$MODEL pulled ✅"
    fi
    MODELS_PULLED+=("$MODEL")
done

# ── determine current model ───────────────────────────────────────────────────
CURRENT_MODEL=""
if [ -f "$HOME/.taris/bot.env" ]; then
    CURRENT_MODEL=$(grep -E '^OLLAMA_MODEL=' "$HOME/.taris/bot.env" 2>/dev/null | cut -d= -f2 | tr -d '"' || true)
fi
if [ -z "$CURRENT_MODEL" ]; then
    CURRENT_MODEL="qwen3.5:latest"
    warn "OLLAMA_MODEL not set in bot.env — using $CURRENT_MODEL as baseline"
fi

# ── build model list ───────────────────────────────────────────────────────────
ALL_MODELS="$CURRENT_MODEL,gemma4:e2b,gemma4:e4b"
info "Benchmarking: $ALL_MODELS"
info "Results will be saved to: $SAVE_PATH"

# ── run benchmark ──────────────────────────────────────────────────────────────
PYTHONPATH="$TARIS_SRC/src" python3 "$BENCH" \
    --model "$ALL_MODELS" \
    --target "$TARGET" \
    --save "$SAVE_PATH"

info ""
info "═══════════════════════════════════════════════════════"
info "Evaluation complete — $TARGET"
info "Results saved: $SAVE_PATH"
info ""
info "Next steps:"
info "  1. Review the quality scores above"
info "  2. If gemma4:e4b quality ≥ 90% across all languages:"
info "       echo 'OLLAMA_MODEL=gemma4:e4b' >> ~/.taris/bot.env"
info "       systemctl --user restart taris-telegram"
info "  3. Run regression tests:"
info "       PYTHONPATH=$TARIS_SRC/src python3 $TARIS_SRC/src/tests/test_voice_regression.py"
info "═══════════════════════════════════════════════════════"
