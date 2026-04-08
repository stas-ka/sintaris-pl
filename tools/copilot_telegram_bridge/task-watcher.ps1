# task-watcher.ps1 -- Real-time Telegram task watcher for VS Code Copilot
#
# Polls the VPS task queue directly over HTTPS (primary) or via SSH tunnel
# (fallback, when mcp-tunnel.ps1 is running on port 3002).
# When a new /task arrives from Telegram, opens VS Code Copilot Chat with
# the task text pre-filled and auto-submits it so Copilot starts immediately.
#
# Uses /tasks/pop (consume-once) so each task triggers exactly once.
# Tasks queued before the watcher started are skipped (stale).
#
# Prerequisites:
#   1. VS Code with github.copilot-chat extension must be open
#   2. .env file in the same directory (TELEGRAM_BOT_TOKEN, VPS_MCP_HOST)
#      -- if missing, falls back to tunnel-only mode
#
# Run: .\task-watcher.ps1
# Stop: Ctrl+C

param(
    [int]$PollInterval = 5,          # seconds between queue checks
    [int]$SubmitDelayMs = 1200,      # ms to wait before auto-submitting
    [switch]$NoAutoSubmit,           # show notification only, don't press Enter
    [switch]$NoSkipStale             # also fire tasks queued before watcher started
)

# Load .env from same directory (TELEGRAM_BOT_TOKEN, VPS_MCP_HOST)
$envFile = Join-Path $PSScriptRoot ".env"
$botToken = ""
$vpsHost  = "dev2null.website"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*TELEGRAM_BOT_TOKEN\s*=\s*(.+)') { $botToken = $Matches[1].Trim() }
        if ($_ -match '^\s*VPS_MCP_HOST\s*=\s*(.+)')       { $vpsHost  = $Matches[1].Trim() }
    }
}

# Primary URL: HTTPS direct (no tunnel needed); fallback: SSH tunnel
$TASKS_POP_HTTPS   = if ($botToken) { "https://$vpsHost/tasks/pop?token=$botToken" } else { "" }
$TASKS_POP_TUNNEL  = "http://127.0.0.1:3002/tasks/pop"
$VSCODE_CHAT_URI   = "vscode://GitHub.copilot-chat/chat?query="

# Determine active polling URL at startup
$TASKS_POP_URL = $TASKS_POP_HTTPS
$usingHTTPS    = $true
if (-not $TASKS_POP_HTTPS) {
    $TASKS_POP_URL = $TASKS_POP_TUNNEL
    $usingHTTPS    = $false
}

# Only fire tasks newer than this timestamp (skip stale queue from before startup)
$startupTs = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$pollOk    = $false

function Show-Toast([string]$title, [string]$body) {
    # Windows 10/11 toast via WScript ballon or fallback console alert
    try {
        Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
        $balloon = New-Object System.Windows.Forms.NotifyIcon
        $balloon.Icon            = [System.Drawing.SystemIcons]::Information
        $balloon.BalloonTipTitle = $title
        $balloon.BalloonTipText  = $body
        $balloon.Visible         = $true
        $balloon.ShowBalloonTip(5000)
        Start-Sleep -Milliseconds 200
        $balloon.Dispose()
    } catch {
        Write-Host "  [NOTIFY] $title -- $body"
    }
}

function Open-CopilotTask([string]$taskText) {
    $encoded = [System.Uri]::EscapeDataString($taskText)
    $uri     = "$VSCODE_CHAT_URI$encoded"

    Write-Host "  -> Opening VS Code Copilot: $uri" -ForegroundColor Cyan
    Start-Process $uri

    if (-not $NoAutoSubmit) {
        Start-Sleep -Milliseconds $SubmitDelayMs
        try {
            $wsh = New-Object -ComObject WScript.Shell
            # Bring VS Code window to front and submit the pre-filled query
            if ($wsh.AppActivate("Visual Studio Code")) {
                Start-Sleep -Milliseconds 400
                $wsh.SendKeys("{ENTER}")
                Write-Host "  -> Submitted (Enter sent to VS Code)" -ForegroundColor Green
            } else {
                Write-Host "  -> VS Code not found -- open it and press Enter manually" -ForegroundColor Yellow
            }
        } catch {
            Write-Host "  -> Auto-submit failed ($_) -- press Enter in Copilot chat manually" -ForegroundColor Yellow
        }
    }
}

Write-Host ""
Write-Host "+---------------------------------------------------+" -ForegroundColor Cyan
Write-Host "|  Taris Task Watcher - live Copilot task trigger   |" -ForegroundColor Cyan
Write-Host "+---------------------------------------------------+" -ForegroundColor Cyan
if ($usingHTTPS) {
    Write-Host "  Primary: HTTPS https://$vpsHost (no tunnel needed)" -ForegroundColor Green
    Write-Host "  Fallback: SSH tunnel http://127.0.0.1:3002"
} else {
    Write-Host "  Mode: SSH tunnel only (no TELEGRAM_BOT_TOKEN in .env)" -ForegroundColor Yellow
    Write-Host "  Requires: mcp-tunnel.ps1 running"
}
Write-Host "  Polling every ${PollInterval}s (consume-once via /tasks/pop)"
if ($NoSkipStale) {
    Write-Host "  Stale tasks: INCLUDED (will fire old queued tasks)"
} else {
    Write-Host "  Stale tasks: skipped (only tasks sent after watcher start)"
}
if ($NoAutoSubmit) {
    Write-Host "  Auto-submit: OFF (press Enter in Copilot chat manually)"
} else {
    Write-Host "  Auto-submit: ON (Enter sent to VS Code after ${SubmitDelayMs}ms)"
}
Write-Host "  Press Ctrl+C to stop"
Write-Host ""

while ($true) {
    # Try primary URL first; if it fails and we have a tunnel fallback, try that
    $resp    = $null
    $fetchOk = $false

    try {
        $resp    = Invoke-RestMethod -Uri $TASKS_POP_URL -TimeoutSec 3 -ErrorAction Stop
        $fetchOk = $true
    } catch {
        if ($usingHTTPS -and $TASKS_POP_TUNNEL) {
            # HTTPS failed -- try tunnel fallback silently
            try {
                $resp    = Invoke-RestMethod -Uri $TASKS_POP_TUNNEL -TimeoutSec 2 -ErrorAction Stop
                $fetchOk = $true
                if ($pollOk) {
                    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] HTTPS unreachable, using tunnel fallback" -ForegroundColor Yellow
                }
            } catch { }
        }
    }

    if ($fetchOk) {
        if (-not $pollOk) {
            Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Connected -- watching for tasks..." -ForegroundColor Green
            $pollOk = $true
        }

        # pop returns {"status":"none"} when queue is empty, or {text, from_user, ts}
        if ($resp -and $resp.text -and $resp.status -ne "none") {
            $taskTs   = [double]$resp.ts
            $taskText = $resp.text
            $sender   = $resp.from_user

            # Skip tasks queued before this watcher instance started (stale)
            if (-not $NoSkipStale -and $taskTs -lt $startupTs) {
                Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Skipping stale task from @${sender}: '$taskText' (queued before startup)" -ForegroundColor DarkGray
            } else {
                Write-Host ""
                Write-Host "[$(Get-Date -Format 'HH:mm:ss')] *** NEW TASK from @$sender ***" -ForegroundColor Magenta
                Write-Host "  Task: $taskText" -ForegroundColor White

                Show-Toast "Copilot Task" "From @${sender}: $taskText"
                Open-CopilotTask $taskText
            }
        }
    } else {
        if ($pollOk) {
            Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Connection lost -- retrying..." -ForegroundColor Yellow
            $pollOk = $false
        } else {
            Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Waiting for connection..." -ForegroundColor DarkGray
        }
    }

    Start-Sleep $PollInterval
}

