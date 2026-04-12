#!/bin/bash
# Source this to deploy to SintAItion via Tailscale (from outside home network)
# Usage (from project root): source tools/use_tailscale.sh
# Requires: OPENCLAW1_TAILSCALE_IP in .env
if [[ -f ".env" ]]; then
  set -a && source .env && set +a
fi
export OPENCLAW1_HOST="${OPENCLAW1_TAILSCALE_IP:?OPENCLAW1_TAILSCALE_IP not set — add it to .env}"
echo "✅ OPENCLAW1_HOST → Tailscale ($OPENCLAW1_HOST) — remote access active"
