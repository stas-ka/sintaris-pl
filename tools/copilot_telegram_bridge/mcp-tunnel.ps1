# mcp-tunnel.ps1 — Open SSH tunnel to VPS MCP bridge
# Run this ONCE before starting VS Code (keep the window open)
# VS Code mcp.json: "telegramBridge-vps" connects to http://localhost:3001/sse

$VPS_HOST = "dev2null.website"
$VPS_USER = "boh"
$VPS_PWD  = "zusammen2019"
$LOCAL_PORT = 3001
$TASK_API_PORT = 3002

Write-Host "Opening SSH tunnel: localhost:$LOCAL_PORT -> $VPS_HOST:$LOCAL_PORT (MCP bridge)"
Write-Host "                    localhost:$TASK_API_PORT -> $VPS_HOST:$TASK_API_PORT (task API)"
Write-Host "Keep this window open. Press Ctrl+C to close the tunnel."
Write-Host ""

# -N : no remote command (just tunnel)
# -L : local port forwarding
plink -pw $VPS_PWD -batch -N -L "${LOCAL_PORT}:127.0.0.1:${LOCAL_PORT}" -L "${TASK_API_PORT}:127.0.0.1:${TASK_API_PORT}" "${VPS_USER}@${VPS_HOST}"
