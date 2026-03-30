#!/usr/bin/env bash
# =============================================================================
# update_picoclaw.sh — Deploy / Update Taris to PicoClaw (Raspberry Pi) target
# =============================================================================
# Interactive script: backup → deploy packages → restart → smoke-tests.
# Runs from the developer machine using SSH (sshpass) to reach the Pi.
#
# Usage:
#   bash src/setup/update_picoclaw.sh [options]
#
# Options:
#   --target pi2    Engineering Pi: OpenClawPI2 (default; test here first)
#   --target pi1    Production Pi: OpenClawPI   (requires confirmation)
#   --host <name>   Override Pi hostname (auto: OpenClawPI2.local / OpenClawPI.local)
#   --yes           Skip confirmation prompts (non-interactive / CI mode)
#   --no-backup     Skip pre-deploy backup (⚠ only for rapid iteration)
#   --no-tests      Skip post-deploy smoke tests
#   --upgrade-picoclaw  Also upgrade the picoclaw Go binary from GitHub
#   -h, --help
#
# Requirements:
#   sshpass installed on developer machine:  sudo apt-get install sshpass
#   Credentials read from .credentials/.taris_env or prompted interactively.
#   Variables:  DEV_HOSTPWD (pi2)  PROD_HOSTPWD or PROD_HOSTPWD (pi1)
# =============================================================================

set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────────────
G="\033[32m"; Y="\033[33m"; R="\033[31m"; B="\033[34m"; C="\033[36m"; N="\033[0m"
ok()    { echo -e "${G}[OK]${N}   $*"; }
info()  { echo -e "${B}[..]${N}   $*"; }
warn()  { echo -e "${Y}[!]${N}    $*"; }
fail()  { echo -e "${R}[FAIL]${N} $*"; exit 1; }
hdr()   { echo -e "\n${C}━━━  $*  ━━━${N}"; }
ask()   { printf "${Y}[?]${N}    $* [y/N] "; read -r _ANS; [[ "${_ANS,,}" == y* ]]; }

# ── Locate project root ───────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SRC="${PROJECT}/src"

# ── Defaults ─────────────────────────────────────────────────────────────────
TARGET="pi2"
PI_HOST=""
YES=false
NO_BACKUP=false
NO_TESTS=false
UPGRADE_PICOCLAW=false
PI_USER="stas"
TARIS_HOME_PI="/home/stas/.taris"
PI_SERVICES=(taris-telegram taris-web)

# ── Arg parsing ───────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) TARGET="$2"; shift 2 ;;
    --host)   PI_HOST="$2"; shift 2 ;;
    --yes|-y) YES=true; shift ;;
    --no-backup) NO_BACKUP=true; shift ;;
    --no-tests)  NO_TESTS=true; shift ;;
    --upgrade-picoclaw) UPGRADE_PICOCLAW=true; shift ;;
    -h|--help)
      sed -n '2,30p' "${BASH_SOURCE[0]}" | grep '^#' | sed 's/^# *//'
      exit 0 ;;
    *) warn "Unknown option: $1"; shift ;;
  esac
done

[[ "$TARGET" != "pi2" && "$TARGET" != "pi1" ]] && \
  fail "Invalid --target '$TARGET'. Use: pi2 (engineering) or pi1 (production)"

# ── Auto-detect hostname ──────────────────────────────────────────────────────
if [[ -z "$PI_HOST" ]]; then
  # Read from .env first (DEV_HOST / PROD_HOST), fallback to .local mDNS
  _ENV="${PROJECT}/.env"
  if [[ -f "$_ENV" ]]; then
    if [[ "$TARGET" == "pi2" ]]; then
      _H=$(grep -E '^DEV_HOST=' "$_ENV" 2>/dev/null | cut -d'=' -f2- | tr -d '"' || true)
    else
      _H=$(grep -E '^PROD_HOST=' "$_ENV" 2>/dev/null | cut -d'=' -f2- | tr -d '"' || true)
    fi
    [[ -n "$_H" ]] && PI_HOST="${_H}.local" || true
  fi
  # Fallback defaults
  [[ -z "$PI_HOST" ]] && { [[ "$TARGET" == "pi2" ]] && PI_HOST="OpenClawPI2.local" || PI_HOST="OpenClawPI.local"; }
fi

# ── Load credentials ─────────────────────────────────────────────────────────
CREDS_FILE="${PROJECT}/.credentials/.taris_env"
ENV_FILE="${PROJECT}/.env"
PI_PWD=""

# Try .credentials first, then .env, then prompt
for _cfile in "$CREDS_FILE" "$ENV_FILE"; do
  [[ -f "$_cfile" ]] || continue
  if [[ "$TARGET" == "pi2" ]]; then
    # Support both naming conventions: DEV_HOSTPWD and DEV_HOST_PWD
    PI_PWD=$(grep -E '^DEV_HOSTPWD=' "$_cfile" 2>/dev/null | cut -d'=' -f2- | tr -d '"' || true)
    [[ -z "$PI_PWD" ]] && \
      PI_PWD=$(grep -E '^DEV_HOST_PWD=' "$_cfile" 2>/dev/null | cut -d'=' -f2- | tr -d '"' || true)
  else
    PI_PWD=$(grep -E '^PROD_HOSTPWD=' "$_cfile" 2>/dev/null | cut -d'=' -f2- | tr -d '"' || true)
    [[ -z "$PI_PWD" ]] && \
      PI_PWD=$(grep -E '^PROD_HOST_PWD=' "$_cfile" 2>/dev/null | cut -d'=' -f2- | tr -d '"' || true)
  fi
  [[ -n "$PI_PWD" ]] && break
done
if [[ -z "$PI_PWD" ]]; then
  printf "Enter SSH password for ${PI_USER}@${PI_HOST}: "
  read -rs PI_PWD; echo ""
fi

# ── Check sshpass is available ────────────────────────────────────────────────
command -v sshpass >/dev/null 2>&1 || fail "sshpass not installed. Run: sudo apt-get install sshpass"

# ── Remote helpers ────────────────────────────────────────────────────────────
_ssh() { sshpass -p "$PI_PWD" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
           "${PI_USER}@${PI_HOST}" "$@"; }
_scp() { sshpass -p "$PI_PWD" scp -o StrictHostKeyChecking=no -r "$@"; }
_sudo() { _ssh "echo '$PI_PWD' | sudo -S $*"; }

# ── Connectivity check ────────────────────────────────────────────────────────
hdr "Connectivity"
_ssh "echo connected" >/dev/null 2>&1 || fail "Cannot reach ${PI_USER}@${PI_HOST} — check host/password"
ok "Connected to ${PI_HOST}"

# ── Version detection ─────────────────────────────────────────────────────────
SRC_VER=$(grep 'BOT_VERSION' "${SRC}/core/bot_config.py" 2>/dev/null | head -1 | cut -d'"' -f2 || echo "?")
DEPLOYED_VER=$(_ssh "grep BOT_VERSION ${TARIS_HOME_PI}/core/bot_config.py 2>/dev/null | head -1 | cut -d'\"' -f2" 2>/dev/null || echo "?")

# ── Header ────────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║      Taris Bot — PicoClaw (Pi) Update / Deploy         ║"
echo "╚══════════════════════════════════════════════════════════╝"
if [[ "$TARGET" == "pi2" ]]; then
  echo "  Target   : PI2 / OpenClawPI2 (engineering)"
else
  echo "  Target   : PI1 / OpenClawPI  (production)"
fi
echo "  Host     : ${PI_HOST}  (user: ${PI_USER})"
echo "  Source   : ${SRC_VER}"
echo "  Deployed : ${DEPLOYED_VER}"
echo ""

# ── Confirmation ──────────────────────────────────────────────────────────────
if [[ "$YES" == false ]]; then
  if [[ "$TARGET" == "pi1" ]]; then
    echo -e "${R}  ⚠  PRODUCTION TARGET — OpenClawPI (PI1)${N}"
    echo "  Only deploy here after PI2 has been tested!"
    echo "  PI1 must be on the 'master' branch."
    echo ""
  fi
  ask "Proceed with deployment to ${TARGET} (${PI_HOST})?" || { echo "Aborted."; exit 0; }
fi

# ── Step 1: Backup ────────────────────────────────────────────────────────────
hdr "Step 1/7 — Pre-deploy backup"
if [[ "$NO_BACKUP" == true ]]; then
  warn "Skipping backup (--no-backup)"
else
  TS=$(date +%Y%m%d_%H%M%S)
  BNAME="taris_backup_${TARGET}_v${DEPLOYED_VER}_${TS}"
  BACKUP_LOCAL="${PROJECT}/backup/snapshots/${BNAME}"
  mkdir -p "$BACKUP_LOCAL"

  _ssh "tar czf /tmp/${BNAME}.tar.gz \
    -C ${TARIS_HOME_PI} \
    --exclude='vosk-model-*' --exclude='*.onnx' --exclude='ggml-*.bin' \
    --exclude='*/__pycache__' --exclude='*.pyc' \
    . 2>/dev/null && echo BACKUP_OK"
  _scp "${PI_USER}@${PI_HOST}:/tmp/${BNAME}.tar.gz" "${BACKUP_LOCAL}/"
  _ssh "rm /tmp/${BNAME}.tar.gz"

  BACKUP_SIZE=$(du -sh "${BACKUP_LOCAL}/${BNAME}.tar.gz" 2>/dev/null | cut -f1 || echo "?")
  ok "Backup saved: backup/snapshots/${BNAME}/ (${BACKUP_SIZE})"

  ls -dt "${PROJECT}/backup/snapshots/taris_backup_${TARGET}_"* 2>/dev/null | \
    tail -n +4 | xargs rm -rf 2>/dev/null || true
fi

# ── Step 2: Data directory check ─────────────────────────────────────────────
hdr "Step 2/7 — Data directory check"
DATA_CHECK=$(_ssh "
  missing=()
  for d in calendar notes contacts screens web/templates; do
    [[ -d ${TARIS_HOME_PI}/\$d ]] || missing+=(\"\$d\")
  done
  for f in taris.db bot.env; do
    [[ -f ${TARIS_HOME_PI}/\$f ]] || missing+=(\"\$f\")
  done
  [[ \${#missing[@]} -gt 0 ]] && echo \"MISSING: \${missing[*]}\" || echo OK
" 2>/dev/null)
if [[ "$DATA_CHECK" == OK ]]; then
  ok "All data dirs present on ${PI_HOST}"
else
  warn "On ${PI_HOST}: ${DATA_CHECK}"
  if [[ "$YES" == false ]]; then
    ask "Continue anyway?" || { echo "Aborted."; exit 1; }
  fi
fi

# ── Step 3: Optionally upgrade picoclaw binary ───────────────────────────────
hdr "Step 3/7 — PicoClaw binary"
if [[ "$UPGRADE_PICOCLAW" == true ]]; then
  info "Upgrading picoclaw binary..."
  _ssh "
    ARCH=\$(uname -m)
    URL=\"https://github.com/sipeed/picoclaw/releases/latest/download/picoclaw_\${ARCH}.deb\"
    wget -q \"\$URL\" -O /tmp/picoclaw.deb
    echo '$PI_PWD' | sudo -S dpkg -i /tmp/picoclaw.deb
    rm /tmp/picoclaw.deb
    picoclaw version 2>/dev/null || true
  "
  ok "PicoClaw binary upgraded"
else
  PICOCLAW_VER=$(_ssh "picoclaw version 2>/dev/null || echo 'not installed'" || echo "?")
  ok "PicoClaw binary: ${PICOCLAW_VER} (pass --upgrade-picoclaw to upgrade)"
fi

# ── Step 4: Deploy source files ───────────────────────────────────────────────
hdr "Step 4/7 — Deploy source files"

# Ensure package directories exist on Pi
_ssh "
  for pkg in core telegram features ui security; do
    mkdir -p ${TARIS_HOME_PI}/\$pkg
    touch ${TARIS_HOME_PI}/\$pkg/__init__.py
  done
  mkdir -p ${TARIS_HOME_PI}/tests/voice/results \
           ${TARIS_HOME_PI}/screens \
           ${TARIS_HOME_PI}/web/templates \
           ${TARIS_HOME_PI}/web/static
"

# Python packages
for pkg in core telegram features ui security; do
  [[ -d "${SRC}/${pkg}" ]] && \
    _scp "${SRC}/${pkg}/"*.py "${PI_USER}@${PI_HOST}:${TARIS_HOME_PI}/${pkg}/" && \
    info "  ${pkg}/*.py" || true
done

# Entry points
for f in bot_web.py telegram_menu_bot.py voice_assistant.py gmail_digest.py; do
  [[ -f "${SRC}/${f}" ]] && \
    _scp "${SRC}/${f}" "${PI_USER}@${PI_HOST}:${TARIS_HOME_PI}/${f}" && \
    info "  ${f}" || true
done

# Data files
_scp "${SRC}/strings.json" "${SRC}/release_notes.json" \
     "${PI_USER}@${PI_HOST}:${TARIS_HOME_PI}/"
info "  strings.json release_notes.json"

# Screens
[[ -d "${SRC}/screens" ]] && \
  _scp "${SRC}/screens" "${PI_USER}@${PI_HOST}:${TARIS_HOME_PI}/" && \
  info "  screens/" || true

# Web
[[ -d "${SRC}/web/templates" ]] && \
  _scp "${SRC}/web/templates" "${PI_USER}@${PI_HOST}:${TARIS_HOME_PI}/web/" && \
  info "  web/templates/" || true
[[ -d "${SRC}/web/static" ]] && \
  _scp "${SRC}/web/static" "${PI_USER}@${PI_HOST}:${TARIS_HOME_PI}/web/" && \
  info "  web/static/" || true

# Tests
[[ -d "${SRC}/tests" ]] && \
  _scp "${SRC}/tests" "${PI_USER}@${PI_HOST}:${TARIS_HOME_PI}/" && \
  info "  tests/" || true

ok "All files deployed to ${PI_HOST}:${TARIS_HOME_PI}"

# ── Step 5: Service files ────────────────────────────────────────────────────
hdr "Step 5/7 — Service files"
SVC_UPDATED=false
for svc in taris-telegram taris-web taris-voice; do
  SVC_SRC="${SRC}/services/${svc}.service"
  [[ -f "$SVC_SRC" ]] || continue
  _scp "$SVC_SRC" "${PI_USER}@${PI_HOST}:/tmp/${svc}.service"
  CHANGED=$(_ssh "
    if ! cmp -s /tmp/${svc}.service /etc/systemd/system/${svc}.service 2>/dev/null; then
      echo '$PI_PWD' | sudo -S cp /tmp/${svc}.service /etc/systemd/system/${svc}.service
      echo UPDATED
    fi
    rm -f /tmp/${svc}.service
  " 2>/dev/null || echo "")
  [[ "$CHANGED" == *UPDATED* ]] && SVC_UPDATED=true && info "  Updated: ${svc}.service" || true
done
if [[ "$SVC_UPDATED" == true ]]; then
  _ssh "echo '$PI_PWD' | sudo -S systemctl daemon-reload"
  ok "Service files updated, daemon reloaded"
else
  ok "Service files unchanged"
fi

# ── Step 6: Restart services ─────────────────────────────────────────────────
hdr "Step 6/7 — Restart services"
_ssh "echo '$PI_PWD' | sudo -S systemctl restart taris-telegram taris-web 2>/dev/null || true"
sleep 5
JOURNAL=$(_ssh "journalctl -u taris-telegram -n 20 --no-pager 2>/dev/null" || true)
echo "$JOURNAL" | tail -8

if echo "$JOURNAL" | grep -q "Polling Telegram"; then
  ok "Service started and polling Telegram ✓"
else
  fail "Service did NOT reach 'Polling Telegram' state — check journal above"
fi

# ── Step 7: Smoke tests ──────────────────────────────────────────────────────
hdr "Step 7/7 — Smoke tests"
if [[ "$NO_TESTS" == true ]]; then
  warn "Skipping smoke tests (--no-tests)"
else
  # Run each smoke test individually (--test accepts a single substring filter)
  SMOKE_TESTS="model_files_present i18n_string_coverage bot_name_injection note_edit_append_replace"
  SMOKE_FAIL=0
  for T in $SMOKE_TESTS; do
    RESULT=$(_ssh \
      "PYTHONPATH=${TARIS_HOME_PI} python3 ${TARIS_HOME_PI}/tests/test_voice_regression.py \
       --test ${T} 2>&1 | grep -E 'PASS|FAIL|SKIP|WARN' | tail -2" 2>/dev/null || echo "FAIL runner error")
    echo "  $T: $RESULT"
    echo "$RESULT" | grep -q "FAIL" && SMOKE_FAIL=$((SMOKE_FAIL+1)) || true
  done
  if [[ $SMOKE_FAIL -gt 0 ]]; then
    warn "$SMOKE_FAIL smoke test(s) FAILED — review output above"
  else
    ok "Smoke tests passed ✓"
  fi
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║                 Deployment Summary                      ║"
echo "╚══════════════════════════════════════════════════════════╝"
DEPLOYED_NEW=$(_ssh "grep BOT_VERSION ${TARIS_HOME_PI}/core/bot_config.py 2>/dev/null | head -1 | cut -d'\"' -f2" || echo "?")
if [[ "$TARGET" == "pi2" ]]; then
  echo "  Target  : PI2 / OpenClawPI2 (engineering)"
  echo "  Host    : ${PI_HOST}"
  echo "  Version : ${DEPLOYED_VER} → ${DEPLOYED_NEW}"
  echo ""
  echo "  Next steps:"
  echo "    1. Test the bot in Telegram"
  echo "    2. Run full regression on PI2:"
  echo "       bash src/setup/run_tests_picoclaw.sh --target pi2"
  echo "    3. After tests pass, deploy to PI1:"
  echo "       bash src/setup/update_picoclaw.sh --target pi1"
else
  echo "  Target  : PI1 / OpenClawPI (production)"
  echo "  Host    : ${PI_HOST}"
  echo "  Version : ${DEPLOYED_VER} → ${DEPLOYED_NEW}"
  echo ""
  echo -e "  ${G}PI1 deployed and verified ✅${N}"
fi
echo ""
