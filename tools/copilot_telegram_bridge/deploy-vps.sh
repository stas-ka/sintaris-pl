#!/usr/bin/env bash
# ============================================================
# deploy-vps.sh — Deploy Copilot Telegram MCP Bridge to VPS
# Usage: bash tools/copilot_telegram_bridge/deploy-vps.sh
# ============================================================
set -e

VPS_HOST="dev2null.website"
VPS_USER="boh"
VPS_PWD="zusammen2019"
DEPLOY_DIR="/opt/copilot_docker"

PLINK="plink -pw $VPS_PWD -batch"
PSCP="pscp -pw $VPS_PWD -batch"

echo "=== Copilot MCP Bridge — VPS Deploy ==="
echo "Target: $VPS_USER@$VPS_HOST:$DEPLOY_DIR"
echo ""

# 1. Create remote directory
echo "[1/6] Creating $DEPLOY_DIR on VPS..."
$PLINK $VPS_USER@$VPS_HOST "echo $VPS_PWD | sudo -S mkdir -p $DEPLOY_DIR && echo $VPS_PWD | sudo -S chown $VPS_USER:$VPS_USER $DEPLOY_DIR"

# 2. Upload Docker files
echo "[2/6] Uploading Docker files..."
$PSCP tools/copilot_telegram_bridge/Dockerfile       $VPS_USER@$VPS_HOST:$DEPLOY_DIR/
$PSCP tools/copilot_telegram_bridge/docker-compose.yml  $VPS_USER@$VPS_HOST:$DEPLOY_DIR/
$PSCP tools/copilot_telegram_bridge/.env             $VPS_USER@$VPS_HOST:$DEPLOY_DIR/
$PLINK $VPS_USER@$VPS_HOST "chmod 600 $DEPLOY_DIR/.env"

# 3. Upload Python scripts
echo "[3/6] Uploading MCP server scripts..."
$PLINK $VPS_USER@$VPS_HOST "mkdir -p $DEPLOY_DIR/scripts"
$PSCP tools/copilot_telegram_bridge/scripts/mcp_server.py       $VPS_USER@$VPS_HOST:$DEPLOY_DIR/scripts/
$PSCP tools/copilot_telegram_bridge/scripts/telegram_bridge.py  $VPS_USER@$VPS_HOST:$DEPLOY_DIR/scripts/

# 4. Install systemd service
echo "[4/6] Installing systemd service..."
$PSCP tools/copilot_telegram_bridge/copilot-mcp-bridge.service  $VPS_USER@$VPS_HOST:/tmp/copilot-mcp-bridge.service
$PLINK $VPS_USER@$VPS_HOST "echo $VPS_PWD | sudo -S cp /tmp/copilot-mcp-bridge.service /etc/systemd/system/ && echo $VPS_PWD | sudo -S systemctl daemon-reload && echo $VPS_PWD | sudo -S systemctl enable copilot-mcp-bridge"

# 5. Build Docker image on VPS
echo "[5/6] Building Docker image on VPS..."
$PLINK $VPS_USER@$VPS_HOST "cd $DEPLOY_DIR && echo $VPS_PWD | sudo -S docker compose build --no-cache"

# 6. Start the service
echo "[6/6] Starting service..."
$PLINK $VPS_USER@$VPS_HOST "echo $VPS_PWD | sudo -S systemctl restart copilot-mcp-bridge && sleep 5"

# Verify
echo ""
echo "=== Verifying deployment ==="
$PLINK $VPS_USER@$VPS_HOST "sudo docker ps --filter name=copilot-mcp-bridge --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"

echo ""
echo "=== Done! ==="
echo ""
echo "To use from VS Code, open an SSH tunnel in a terminal:"
echo "  plink -pw zusammen2019 -batch -N -L 3001:127.0.0.1:3001 boh@dev2null.website"
echo ""
echo "Then reload VS Code — telegramBridge-vps will connect to http://localhost:3001/sse"
