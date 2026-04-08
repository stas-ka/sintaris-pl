# task-watcher.ps1 -- Real-time Telegram task watcher for VS Code Copilot
#
# Polls the VPS task queue (via SSH tunnel on port 3002) every few seconds.
# When a new /task arrives from Telegram, opens VS Code Copilot Chat with
# the task text pre-filled and auto-submits it so Copilot starts immediately.
#
# Prerequisites:
#   1. mcp-tunnel.ps1 must be running (port 3002 forwarded)
#   2. VS Code with github.copilot-chat extension must be open
#
# Run: .\task-watcher.ps1
# Stop: Ctrl+C

param(
    [int]$PollInterval = 5,          # seconds between queue checks
    [int]$SubmitDelayMs = 1200,      # ms to wait before auto-submitting
    [switch]$NoAutoSubmit            # show notification only, don't press Enter
)

$TASKS_PEEK_URL  = "http://127.0.0.1:3002/tasks/peek"
$VSCODE_CHAT_URI = "vscode://GitHub.copilot-chat/chat?query="

$lastTriggeredTs = $null
$pollOk          = $false

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
Write-Host "  Polling http://127.0.0.1:3002 every ${PollInterval}s"
Write-Host "  Requires: mcp-tunnel.ps1 running + VS Code open"
if ($NoAutoSubmit) {
    Write-Host "  Auto-submit: OFF (press Enter in Copilot chat manually)"
} else {
    Write-Host "  Auto-submit: ON (Enter sent to VS Code after ${SubmitDelayMs}ms)"
}
Write-Host "  Press Ctrl+C to stop"
Write-Host ""

while ($true) {
    try {
        $resp = Invoke-RestMethod -Uri $TASKS_PEEK_URL -TimeoutSec 3 -ErrorAction Stop

        if (-not $pollOk) {
            Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Tunnel OK -- watching for tasks..." -ForegroundColor Green
            $pollOk = $true
        }

        # peek returns a list; take the first (newest) item
        $task = if ($resp -is [array]) { $resp[0] } else { $resp }

        # New task if ts differs from last triggered
        if ($task -and $task.text -and $task.ts -ne $null -and $task.ts -ne $lastTriggeredTs) {
            $lastTriggeredTs = $task.ts
            $taskText = $task.text
            $sender   = $task.from_user

            Write-Host ""
            Write-Host "[$(Get-Date -Format 'HH:mm:ss')] *** NEW TASK from @$sender ***" -ForegroundColor Magenta
            Write-Host "  Task: $taskText" -ForegroundColor White

            Show-Toast "Copilot Task" "From @${sender}: $taskText"
            Open-CopilotTask $taskText
        }
    } catch {
        if ($pollOk) {
            Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Tunnel lost -- waiting..." -ForegroundColor Yellow
            $pollOk = $false
        } else {
            Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Waiting for tunnel (mcp-tunnel.ps1)..." -ForegroundColor DarkGray
        }
    }

    Start-Sleep $PollInterval
}

