# eval_gemma4_windows.ps1 — Windows PowerShell helper to run Gemma4 evaluation via SSH
#
# Usage (from Windows, in project root):
#   .\tools\eval_gemma4_windows.ps1 -Target TariStation2
#   .\tools\eval_gemma4_windows.ps1 -Target SintAItion
#
# Prerequisites:
#   - .env loaded (or pass credentials as params)
#   - plink (PuTTY) at C:\Program Files\PuTTY\plink.exe
#   - SSH connectivity to target

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("TariStation2","SintAItion")]
    [string]$Target,

    [string]$SshHost     = "",
    [string]$SshUser     = "stas",
    [string]$SshPassword = "",
    [switch]$SkipUpload   # skip source upload (use existing on target)
)

$ErrorActionPreference = "Stop"

# ── load .env ──────────────────────────────────────────────────────────────────
$envFile = Join-Path $PSScriptRoot ".." ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | Where-Object { $_ -match "^\s*\w+=.+" -and $_ -notmatch "^\s*#" } | ForEach-Object {
        $k, $v = $_ -split "=", 2
        [System.Environment]::SetEnvironmentVariable($k.Trim(), $v.Trim(), "Process")
    }
}

# ── resolve target ──────────────────────────────────────────────────────────────
if ($Target -eq "TariStation2") {
    if (-not $SshHost)     { $SshHost = "TariStation2" }
    if (-not $SshPassword) { $SshPassword = $env:DEV_HOSTPWD }
    $OllamaUrl = "http://127.0.0.1:11434"
} else {
    # SintAItion
    if (-not $SshHost)     { $SshHost = if ($env:OPENCLAW1_TAILSCALE_IP) { $env:OPENCLAW1_TAILSCALE_IP } else { "SintAItion.local" } }
    if (-not $SshPassword) { $SshPassword = $env:OPENCLAW1PWD }
    $OllamaUrl = "http://127.0.0.1:11434"
}

$Plink = "C:\Program Files\PuTTY\plink.exe"
if (-not (Test-Path $Plink)) { $Plink = "plink" }

function Invoke-Remote([string]$Cmd) {
    & "$Plink" -pw "$SshPassword" -batch "$SshUser@$SshHost" "$Cmd"
    if ($LASTEXITCODE -ne 0) { Write-Error "Remote command failed (exit $LASTEXITCODE): $Cmd" }
}

Write-Host "=== Gemma4 Evaluation — $Target ===" -ForegroundColor Cyan
Write-Host "SSH: $SshUser@$SshHost"
Write-Host ""

# ── upload latest benchmark script ─────────────────────────────────────────────
if (-not $SkipUpload) {
    Write-Host "[1/4] Uploading benchmark script..." -ForegroundColor Yellow
    $Pscp = $Plink -replace "plink.exe", "pscp.exe"
    & "$Pscp" -pw "$SshPassword" `
        "src\tests\llm\benchmark_ollama_models.py" `
        "${SshUser}@${SshHost}:/home/$SshUser/projects/sintaris-pl/src/tests/llm/benchmark_ollama_models.py"
    Write-Host "  Script uploaded ✅"
}

# ── pull models ─────────────────────────────────────────────────────────────────
Write-Host "[2/4] Pulling Gemma4 models (this may take several minutes)..." -ForegroundColor Yellow
Invoke-Remote "ollama pull gemma4:e2b"
Invoke-Remote "ollama pull gemma4:e4b"
Write-Host "  Models ready ✅"

# ── run evaluation ──────────────────────────────────────────────────────────────
Write-Host "[3/4] Running benchmark..." -ForegroundColor Yellow
$BenchCmd = "cd ~/projects/sintaris-pl && BENCHMARK_TARGET=$Target PYTHONPATH=src python3 src/tests/llm/benchmark_ollama_models.py --model qwen3.5:latest,gemma4:e2b,gemma4:e4b --target $Target"
Invoke-Remote $BenchCmd

# ── run regression tests ────────────────────────────────────────────────────────
Write-Host "[4/4] Running regression tests (T117-T120)..." -ForegroundColor Yellow
$TestCmd = "cd ~/projects/sintaris-pl && PYTHONPATH=src python3 src/tests/test_voice_regression.py --test t_gemma4"
Invoke-Remote $TestCmd

Write-Host ""
Write-Host "=== Evaluation complete — $Target ===" -ForegroundColor Green
Write-Host ""
Write-Host "If gemma4:e4b quality >= 90%:"
Write-Host "  ssh $SshUser@$SshHost 'echo OLLAMA_MODEL=gemma4:e4b >> ~/.taris/bot.env && systemctl --user restart taris-telegram'"
