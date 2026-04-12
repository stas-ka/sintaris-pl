#!/bin/bash
# Run this after authorizing SintAItion in the Tailscale admin console.
# The authorization URL is shown by `tailscale up` on SintAItion.

set -e
cd "$(dirname "$0")/.."
set -a && source .env && set +a

echo "=== Step 1: Check Tailscale status on SintAItion ==="
STATUS=$(sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no "${OPENCLAW1_USER:-stas}@${OPENCLAW1_LAN_HOST:-SintAItion}" \
    "echo '$OPENCLAW1PWD' | sudo -S tailscale status 2>&1 | head -3")
echo "$STATUS"

if echo "$STATUS" | grep -q "Logged out"; then
    echo ""
    echo "❌ Not yet authorized. Open this URL in your browser:"
    echo "   https://login.tailscale.com/a/1235f28801ae89"
    echo "   Then re-run this script."
    exit 1
fi

echo ""
echo "=== Step 2: Get Tailscale IP ==="
TS_IP=$(sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no "${OPENCLAW1_USER:-stas}@${OPENCLAW1_LAN_HOST:-SintAItion}" \
    "echo '$OPENCLAW1PWD' | sudo -S tailscale ip -4 2>&1")
echo "Tailscale IP: $TS_IP"

echo ""
echo "=== Step 3: Update .env ==="
# Remove old OPENCLAW1_TAILSCALE_IP if present, add new one
grep -v "^OPENCLAW1_TAILSCALE_IP=" .env > /tmp/env_new && mv /tmp/env_new .env
echo "OPENCLAW1_TAILSCALE_IP=$TS_IP" >> .env
echo "Updated .env with OPENCLAW1_TAILSCALE_IP=$TS_IP"

echo ""
echo "=== Step 4: Test SSH over Tailscale ==="
sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no stas@$TS_IP \
    "echo '$OPENCLAW1PWD' | sudo -S tailscale status 2>&1 | head -3 && echo '✅ SSH over Tailscale works!'" 2>&1

echo ""
echo "✅ Setup complete! To deploy from internet:"
echo "   Change OPENCLAW1_HOST=$TS_IP in .env (or use OPENCLAW1_TAILSCALE_IP)"
echo ""
echo "=== Step 5: Also install Tailscale on your travel laptop ==="
echo "   curl -fsSL https://tailscale.com/install.sh | sh"
echo "   sudo tailscale up"
echo "   # Authorize in browser, then: ssh stas@$TS_IP"
