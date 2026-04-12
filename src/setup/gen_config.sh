#!/usr/bin/env bash
# gen_config.sh — generate deployment config files from .env + templates
#
# Usage:
#   bash src/setup/gen_config.sh [--target ts2|ts1|pi1|pi2]
#
# Output: deploy/<target>/ directory with filled config files (gitignored)
# The deploy/ directory is gitignored and must never be committed.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env"
TEMPLATE_DIR="$SCRIPT_DIR/templates"

# --- Parse args ---
TARGET="${1:-ts2}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) TARGET="$2"; shift 2 ;;
    *) shift ;;
  esac
done

# --- Load .env ---
if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: .env not found at $ENV_FILE"
  echo "Copy .env.example to .env and fill in real values."
  exit 1
fi
# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a

# --- Output directory ---
OUT_DIR="$PROJECT_ROOT/deploy/$TARGET"
mkdir -p "$OUT_DIR"
echo "Generating configs for target: $TARGET → $OUT_DIR"

# --- Generate bot.env ---
if command -v envsubst &>/dev/null; then
  envsubst < "$TEMPLATE_DIR/bot.env.template" > "$OUT_DIR/bot.env"
  echo "  ✅ bot.env"
else
  echo "  ⚠️  envsubst not found — falling back to Python"
  python3 -c "
import os, re, sys
with open('$TEMPLATE_DIR/bot.env.template') as f:
    content = f.read()
def replacer(m):
    var = m.group(1); default = m.group(3) or ''
    return os.environ.get(var, default)
content = re.sub(r'\\\${([A-Z0-9_]+)(:-([^}]*))?}', replacer, content)
with open('$OUT_DIR/bot.env', 'w') as f:
    f.write(content)
"
  echo "  ✅ bot.env (via Python)"
fi

# --- Security check: no template placeholders left in generated output ---
if grep -qE '\$\{[A-Z_]+\}' "$OUT_DIR/bot.env" 2>/dev/null; then
  echo ""
  echo "⚠️  WARNING: Unreplaced placeholders found in $OUT_DIR/bot.env:"
  grep -E '\$\{[A-Z_]+\}' "$OUT_DIR/bot.env" || true
  echo "Check that all required variables are set in .env"
fi

echo ""
echo "Generated configs saved to: deploy/$TARGET/ (gitignored)"
echo "Next: copy deploy/$TARGET/bot.env to target ~/.taris/bot.env"
