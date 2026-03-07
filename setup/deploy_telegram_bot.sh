#!/bin/bash
# =============================================================================
# Deploy picoclaw Telegram Menu Bot
# =============================================================================
# Installs pyTelegramBotAPI, deploys telegram_menu_bot.py, disables the
# picoclaw-gateway Telegram channel (to avoid token conflict), and starts
# the new service.
#
# Run from Pi or via plink after pscp-copying to /tmp:
#   bash /tmp/deploy_telegram_bot.sh
# =============================================================================

set -e

PICOCLAW_DIR="/home/stas/.picoclaw"
PICOCLAW_CONFIG="${PICOCLAW_DIR}/config.json"

echo "=============================================="
echo " Picoclaw Telegram Menu Bot — Deploy"
echo "=============================================="

# 1. Install pyTelegramBotAPI
echo ""
echo "[1/5] Installing pyTelegramBotAPI..."
pip3 install --break-system-packages --quiet pyTelegramBotAPI
echo "  pyTelegramBotAPI installed."

# 2. Disable Telegram in picoclaw config.json (avoid token conflict)
echo ""
echo "[2/5] Disabling picoclaw's built-in Telegram channel..."
if [ -f "$PICOCLAW_CONFIG" ]; then
    python3 - << 'PYEOF'
import json, sys
with open('/home/stas/.picoclaw/config.json') as f:
    cfg = json.load(f)
if cfg.get('channels', {}).get('telegram', {}).get('enabled', False):
    cfg['channels']['telegram']['enabled'] = False
    with open('/home/stas/.picoclaw/config.json', 'w') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    print("  telegram.enabled set to false in config.json")
else:
    print("  Already disabled or not present.")
PYEOF
    # Restart picoclaw-gateway so it picks up the change
    systemctl restart picoclaw-gateway 2>/dev/null || true
    echo "  picoclaw-gateway restarted."
else
    echo "  config.json not found at ${PICOCLAW_CONFIG}, skipping."
fi

# 3. Copy service file
echo ""
echo "[3/5] Installing systemd service..."
cp /tmp/picoclaw-telegram.service /etc/systemd/system/picoclaw-telegram.service
systemctl daemon-reload
systemctl enable picoclaw-telegram.service
echo "  Service installed and enabled."

# 4. Fix permissions on log file
touch "${PICOCLAW_DIR}/telegram_bot.log"
chown stas:stas "${PICOCLAW_DIR}/telegram_bot.log"

# 5. Start the service
echo ""
echo "[4/5] Starting picoclaw-telegram service..."
systemctl restart picoclaw-telegram.service
sleep 5
systemctl status picoclaw-telegram --no-pager

echo ""
echo "[5/5] Tailing log (5 lines)..."
tail -10 "${PICOCLAW_DIR}/telegram_bot.log" 2>/dev/null || \
    journalctl -u picoclaw-telegram -n 10 --no-pager

echo ""
echo "======================================"
echo " Done!"
echo " Send /menu to @smartpico_bot"
echo "======================================"
