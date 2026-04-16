#!/bin/bash
# update.sh — Update Taris VPS Docker instance source code and restart
#
# Run from: local machine (Windows: use via WSL or pscp/plink)
# Or run directly on VPS: bash /opt/taris-docker/update.sh
#
# Usage:
#   update.sh            — sync src/ and restart both containers
#   update.sh --no-restart  — sync only, no restart
#   update.sh --web-only    — restart taris-vps-web only (for bot_web.py changes)

set -e

TARIS_DIR="/opt/taris-docker"
SRC_DIR="${TARIS_DIR}/app/src"
COMPOSE="sudo docker compose -f ${TARIS_DIR}/docker-compose.yml"

NO_RESTART=0
WEB_ONLY=0
for arg in "$@"; do
  case $arg in
    --no-restart)  NO_RESTART=1 ;;
    --web-only)    WEB_ONLY=1 ;;
  esac
done

echo "=== Taris VPS Docker Update ==="
echo "Source: ${SRC_DIR}"
echo ""

# Verify source exists
if [ ! -f "${SRC_DIR}/telegram_menu_bot.py" ]; then
  echo "ERROR: Source not found at ${SRC_DIR}"
  echo "  Upload with: pscp -pw PASSWORD -r src/ stas@dev2null.de:/opt/taris-docker/app"
  exit 1
fi

# Show version being deployed
VERSION=$(grep -m1 'BOT_VERSION' "${SRC_DIR}/core/bot_config.py" 2>/dev/null | grep -oP '"\K[^"]+' || echo "unknown")
echo "Deploying version: ${VERSION}"
echo ""

if [ "$NO_RESTART" -eq 1 ]; then
  echo "Source synced (--no-restart: skipping container restart)"
  exit 0
fi

echo "=== Restarting containers ==="
if [ "$WEB_ONLY" -eq 1 ]; then
  sudo docker restart taris-vps-web
  echo "taris-vps-web restarted"
else
  sudo docker restart taris-vps-telegram taris-vps-web
  echo "taris-vps-telegram + taris-vps-web restarted"
fi

sleep 3

echo ""
echo "=== Container status ==="
sudo docker ps | grep taris-vps

echo ""
echo "=== Web UI logs (last 8 lines) ==="
sudo docker logs taris-vps-web 2>&1 | tail -8

echo ""
echo "=== Telegram logs (last 5 lines) ==="
sudo docker logs taris-vps-telegram 2>&1 | tail -5
