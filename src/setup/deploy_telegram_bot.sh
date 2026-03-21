#!/bin/bash
# =============================================================================
# Deploy taris Telegram Menu Bot
# =============================================================================
# Installs pyTelegramBotAPI, deploys telegram_menu_bot.py, disables the
# taris-gateway Telegram channel (to avoid token conflict), and starts
# the new service.
#
# Run from Pi or via plink after pscp-copying to /tmp:
#   bash /tmp/deploy_telegram_bot.sh
# =============================================================================

set -e

TARIS_DIR="/home/stas/.taris"
TARIS_CONFIG="${TARIS_DIR}/config.json"

echo "=============================================="
echo " Taris Telegram Menu Bot — Deploy"
echo "=============================================="

# 1. Install pyTelegramBotAPI
echo ""
echo "[1/5] Installing pyTelegramBotAPI..."
pip3 install --break-system-packages --quiet pyTelegramBotAPI
echo "  pyTelegramBotAPI installed."

# 2. Disable Telegram in taris config.json (avoid token conflict)
echo ""
echo "[2/5] Disabling taris's built-in Telegram channel..."
if [ -f "$TARIS_CONFIG" ]; then
    python3 - << 'PYEOF'
import json, sys
with open('/home/stas/.taris/config.json') as f:
    cfg = json.load(f)
if cfg.get('channels', {}).get('telegram', {}).get('enabled', False):
    cfg['channels']['telegram']['enabled'] = False
    with open('/home/stas/.taris/config.json', 'w') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    print("  telegram.enabled set to false in config.json")
else:
    print("  Already disabled or not present.")
PYEOF
    # Restart taris-gateway so it picks up the change
    systemctl restart taris-gateway 2>/dev/null || true
    echo "  taris-gateway restarted."
else
    echo "  config.json not found at ${TARIS_CONFIG}, skipping."
fi

# 3. Copy service file
echo ""
echo "[3/5] Installing systemd service..."
cp /tmp/taris-telegram.service /etc/systemd/system/taris-telegram.service
systemctl daemon-reload
systemctl enable taris-telegram.service
echo "  Service installed and enabled."

# 4. Fix permissions on log file
touch "${TARIS_DIR}/telegram_bot.log"
chown stas:stas "${TARIS_DIR}/telegram_bot.log"

# 5. Start the service
echo ""
echo "[4/5] Starting taris-telegram service..."
systemctl restart taris-telegram.service
sleep 5
systemctl status taris-telegram --no-pager

echo ""
echo "[5/5] Tailing log (5 lines)..."
tail -10 "${TARIS_DIR}/telegram_bot.log" 2>/dev/null || \
    journalctl -u taris-telegram -n 10 --no-pager

echo ""
echo "======================================"
echo " Done!"
echo " Send /menu to @smartpico_bot"
echo "======================================"
