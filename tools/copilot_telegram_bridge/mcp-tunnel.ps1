# mcp-tunnel.ps1 -- Open SSH tunnel to VPS MCP bridge + start live task watcher
#
# Run this ONCE before starting VS Code (keep the window open).
# VS Code mcp.json: "telegramBridge-vps" connects to http://localhost:3001/sse
#
# With -Watch (default): also starts task-watcher.ps1 so /task from Telegram
# immediately opens VS Code Copilot Chat with the task pre-filled.
#
# Usage:
#   .\mcp-tunnel.ps1           -- tunnel + watcher (recommended)
#   .\mcp-tunnel.ps1 -NoWatch  -- tunnel only (legacy)

param([switch]$NoWatch)

$VPS_HOST      = "dev2null.website"
$VPS_USER      = "boh"
$VPS_PWD       = "zusammen2019"
$LOCAL_PORT    = 3001
$TASK_API_PORT = 3002
$SCRIPT_DIR    = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "Opening SSH tunnel: localhost:$LOCAL_PORT -> $VPS_HOST:$LOCAL_PORT (MCP bridge)"
Write-Host "                    localhost:$TASK_API_PORT -> $VPS_HOST:$TASK_API_PORT (task API)"
if (-not $NoWatch) {
    Write-Host "Task watcher:       starting in new window (closes with this tunnel)"
}
Write-Host "Keep this window open. Press Ctrl+C to close the tunnel."
Write-Host ""

# Start task watcher in a separate window so it runs alongside the tunnel
$watcherProc = $null
if (-not $NoWatch) {
    $watcherScript = Join-Path $SCRIPT_DIR "task-watcher.ps1"
    if (Test-Path $watcherScript) {
        $watcherProc = Start-Process powershell -ArgumentList "-ExecutionPolicy Bypass -File `"$watcherScript`" -PollInterval 5" -PassThru
        Write-Host "[tunnel] Task watcher PID $($watcherProc.Id) started"
    } else {
        Write-Host "[tunnel] task-watcher.ps1 not found -- skipping watcher"
    }
}

try {
    # -N : no remote command (just tunnel)
    # -L : local port forwarding
    plink -pw $VPS_PWD -batch -N -L "${LOCAL_PORT}:127.0.0.1:${LOCAL_PORT}" -L "${TASK_API_PORT}:127.0.0.1:${TASK_API_PORT}" "${VPS_USER}@${VPS_HOST}"
} finally {
    # Stop watcher when tunnel exits
    if ($watcherProc -and -not $watcherProc.HasExited) {
        Write-Host "[tunnel] Stopping task watcher (PID $($watcherProc.Id))..."
        $watcherProc | Stop-Process -Force -ErrorAction SilentlyContinue
    }
}
