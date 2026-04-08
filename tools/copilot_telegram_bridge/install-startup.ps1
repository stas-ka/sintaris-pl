# install-startup.ps1 -- Add task-watcher.ps1 to Windows startup folder
#
# Creates a shortcut in %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
# so task-watcher.ps1 runs at every login. The watcher polls the VPS HTTPS
# endpoint directly (no SSH tunnel needed).
#
# Run once as current user (no elevation required).
# To remove: .\install-startup.ps1 -Remove

param([switch]$Remove)

$SHORTCUT_NAME = "TarisTaskWatcher.lnk"
$STARTUP_DIR   = [Environment]::GetFolderPath("Startup")
$SHORTCUT_PATH = Join-Path $STARTUP_DIR $SHORTCUT_NAME
$SCRIPT_DIR    = Split-Path -Parent $MyInvocation.MyCommand.Path
$WATCHER       = Join-Path $SCRIPT_DIR "task-watcher.ps1"

if ($Remove) {
    if (Test-Path $SHORTCUT_PATH) {
        Remove-Item $SHORTCUT_PATH -Force
        Write-Host "Removed startup shortcut: $SHORTCUT_PATH" -ForegroundColor Green
    } else {
        Write-Host "Shortcut not found (already removed?)" -ForegroundColor Yellow
    }
    exit 0
}

if (-not (Test-Path $WATCHER)) {
    Write-Host "ERROR: task-watcher.ps1 not found at: $WATCHER" -ForegroundColor Red
    exit 1
}

# Create a .lnk shortcut pointing to powershell running the watcher hidden
$wsh     = New-Object -ComObject WScript.Shell
$link    = $wsh.CreateShortcut($SHORTCUT_PATH)
$link.TargetPath       = "powershell.exe"
$link.Arguments        = "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$WATCHER`" -PollInterval 5"
$link.WorkingDirectory = $SCRIPT_DIR
$link.Description      = "Taris Copilot task watcher"
$link.WindowStyle      = 7   # Minimized
$link.Save()

Write-Host "Startup shortcut created: $SHORTCUT_PATH" -ForegroundColor Green
Write-Host ""
Write-Host "Task watcher will start automatically at next login." -ForegroundColor Green
Write-Host "To start it NOW (hidden window):"
Write-Host "  Start-Process powershell -ArgumentList '-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$WATCHER`" -PollInterval 5' -WindowStyle Hidden" -ForegroundColor Cyan
Write-Host ""
Write-Host "To remove: .\install-startup.ps1 -Remove"
