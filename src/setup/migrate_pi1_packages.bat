@echo off
setlocal
:: =============================================================================
:: PI1 Package Structure Migration
:: =============================================================================
:: Migrates /home/stas/.picoclaw/ on PI1 (OpenClawPI) from the old flat layout
:: (all bot_*.py at root) to the new package layout:
::   core/  security/  telegram/  features/  ui/  web/templates/  web/static/
::
:: Prerequisites:
::   - Set HOSTPWD in .env (or override the set command below)
::   - Source .env in your shell, OR ensure %HOSTPWD% is set in the environment
::   - Run from workspace root: src\setup\migrate_pi1_packages.bat
::
:: Deployment order:
::   1. Backup PI1 (tar.gz, models excluded)
::   2. Create package directories
::   3. Deploy packages: core/ security/ telegram/ features/ ui/
::   4. Deploy root entry-points + data files
::   5. Deploy web/ templates + static
::   6. Daemon-reload + restart services
::   7. Smoke check (journal)
:: =============================================================================

set HOST=OpenClawPI
set USER=stas
:: Load password from environment (set by "source .env" or .env.bat)
:: Override here if needed:
:: set PWD=...
set PWD=%HOSTPWD%

set PICOCLAW=/home/stas/.picoclaw
set SRC=src

if "%PWD%"=="" (
    echo ERROR: HOSTPWD not set. Source .env or set HOSTPWD before running.
    exit /b 1
)

echo.
echo ==========================================================================
echo  PI1 Package Structure Migration
echo  Target   : %USER%@%HOST%
echo  Date     : %DATE% %TIME%
echo ==========================================================================

:: ---- 1 / 7  Backup -------------------------------------------------------
echo.
echo [1/7] Creating pre-migration backup on PI1...
plink -pw "%PWD%" -batch %USER%@%HOST% ^
  "BNAME=picoclaw_premig_$(date +%%Y%%m%%d_%%H%%M%%S) && ^
   tar czf /tmp/${BNAME}.tar.gz -C /home/stas/.picoclaw ^
   --exclude=vosk-model-small-ru --exclude=vosk-model-small-de ^
   --exclude='*.onnx' --exclude='ggml-*.bin' ^
   . 2>/dev/null && echo BACKUP_OK: /tmp/${BNAME}.tar.gz || echo BACKUP_FAILED"
if %ERRORLEVEL% neq 0 (
    echo WARNING: Backup step exited non-zero. Continuing anyway...
)

:: ---- 2 / 7  Create directories ------------------------------------------
echo.
echo [2/7] Creating package directories on PI1...
plink -pw "%PWD%" -batch %USER%@%HOST% ^
  "mkdir -p %PICOCLAW%/core %PICOCLAW%/security %PICOCLAW%/telegram ^
            %PICOCLAW%/features %PICOCLAW%/ui ^
            %PICOCLAW%/web/templates %PICOCLAW%/web/static && echo DIRS_OK"
if %ERRORLEVEL% neq 0 ( echo ERROR creating directories. & exit /b 2 )

:: ---- 3 / 7  Deploy packages ---------------------------------------------
echo.
echo [3/7] Deploying Python packages...

echo   core/ ...
pscp -pw "%PWD%" -r %SRC%\core\ %USER%@%HOST%:%PICOCLAW%/core/
if %ERRORLEVEL% neq 0 ( echo ERROR deploying core/. & exit /b 3 )

echo   security/ ...
pscp -pw "%PWD%" -r %SRC%\security\ %USER%@%HOST%:%PICOCLAW%/security/
if %ERRORLEVEL% neq 0 ( echo ERROR deploying security/. & exit /b 3 )

echo   telegram/ ...
pscp -pw "%PWD%" -r %SRC%\telegram\ %USER%@%HOST%:%PICOCLAW%/telegram/
if %ERRORLEVEL% neq 0 ( echo ERROR deploying telegram/. & exit /b 3 )

echo   features/ ...
pscp -pw "%PWD%" -r %SRC%\features\ %USER%@%HOST%:%PICOCLAW%/features/
if %ERRORLEVEL% neq 0 ( echo ERROR deploying features/. & exit /b 3 )

echo   ui/ ...
pscp -pw "%PWD%" -r %SRC%\ui\ %USER%@%HOST%:%PICOCLAW%/ui/
if %ERRORLEVEL% neq 0 ( echo ERROR deploying ui/. & exit /b 3 )

:: ---- 4 / 7  Deploy root entry-points + data -----------------------------
echo.
echo [4/7] Deploying root entry-points and data files...

pscp -pw "%PWD%" %SRC%\telegram_menu_bot.py %USER%@%HOST%:%PICOCLAW%/
pscp -pw "%PWD%" %SRC%\bot_web.py            %USER%@%HOST%:%PICOCLAW%/
pscp -pw "%PWD%" %SRC%\voice_assistant.py    %USER%@%HOST%:%PICOCLAW%/
pscp -pw "%PWD%" %SRC%\gmail_digest.py       %USER%@%HOST%:%PICOCLAW%/
pscp -pw "%PWD%" %SRC%\strings.json          %USER%@%HOST%:%PICOCLAW%/
pscp -pw "%PWD%" %SRC%\release_notes.json    %USER%@%HOST%:%PICOCLAW%/
if %ERRORLEVEL% neq 0 ( echo ERROR deploying root files. & exit /b 4 )

:: ---- 5 / 7  Deploy web assets -------------------------------------------
echo.
echo [5/7] Deploying web assets (templates + static)...

pscp -pw "%PWD%" -r %SRC%\web\templates\ %USER%@%HOST%:%PICOCLAW%/web/templates/
if %ERRORLEVEL% neq 0 ( echo ERROR deploying web/templates/. & exit /b 5 )

pscp -pw "%PWD%" -r %SRC%\web\static\ %USER%@%HOST%:%PICOCLAW%/web/static/
if %ERRORLEVEL% neq 0 ( echo ERROR deploying web/static/. & exit /b 5 )

:: ---- 6 / 7  Clean up old __pycache__ + restart --------------------------
echo.
echo [6/7] Clearing old __pycache__ and restarting services...
plink -pw "%PWD%" -batch %USER%@%HOST% ^
  "find %PICOCLAW% -maxdepth 2 -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null; ^
   echo %PWD% | sudo -S systemctl daemon-reload && ^
   echo %PWD% | sudo -S systemctl restart picoclaw-telegram picoclaw-web && ^
   sleep 5 && echo SERVICES_RESTARTED"
if %ERRORLEVEL% neq 0 ( echo ERROR restarting services. & exit /b 6 )

:: ---- 7 / 7  Smoke check --------------------------------------------------
echo.
echo [7/7] Smoke check - Telegram bot journal:
echo --------------------------------------------------------------------------
plink -pw "%PWD%" -batch %USER%@%HOST% ^
  "journalctl -u picoclaw-telegram -n 20 --no-pager"
echo --------------------------------------------------------------------------
echo.
echo Web service journal:
echo --------------------------------------------------------------------------
plink -pw "%PWD%" -batch %USER%@%HOST% ^
  "journalctl -u picoclaw-web -n 10 --no-pager"
echo --------------------------------------------------------------------------

echo.
echo ==========================================================================
echo  Migration complete.
echo  Verify output above:
echo    Telegram: [INFO] Version : 2026.x.y  +  Polling Telegram...
echo    Web:      Uvicorn running on https://0.0.0.0:8080
echo  NOTE: Old flat bot_*.py files remain at root (harmless - not imported).
echo  Run cleanup later: plink ... "rm ~/.picoclaw/bot_*.py"
echo ==========================================================================

endlocal
