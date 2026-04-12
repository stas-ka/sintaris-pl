#!/bin/bash
# Source this to deploy to SintAItion via LAN (at home)
# Usage (from project root): source tools/use_lan.sh
if [[ -f ".env" ]]; then
  set -a && source .env && set +a
fi
export OPENCLAW1_HOST="${OPENCLAW1_LAN_HOST:-SintAItion}"
echo "✅ OPENCLAW1_HOST → LAN ($OPENCLAW1_HOST) — home network active"
