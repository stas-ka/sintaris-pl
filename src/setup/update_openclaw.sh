#!/usr/bin/env bash
# =============================================================================
# update_openclaw.sh — Deploy / Update Taris to OpenClaw target (TariStation)
# =============================================================================
# Interactive script: backup → deploy all packages → restart → smoke-tests.
# Runs from the developer machine (project root or any subdir of it).
#
# Usage:
#   bash src/setup/update_openclaw.sh [options]
#
# Options:
#   --target ts2    Local TariStation2 (default; uses cp + systemctl --user)
#   --target ts1    Remote TariStation1/SintAItion (uses sshpass + scp + ssh)
#   --yes           Skip confirmation prompts (non-interactive / CI mode)
#   --no-backup     Skip pre-deploy backup (⚠ only for rapid iteration)
#   --no-tests      Skip post-deploy smoke tests
#   --force-restart Restart services even if sync check passes
#   -h, --help
#
# Requirements for --target ts1:
#   Source .env in project root with: OPENCLAW1_HOST  OPENCLAW1_USER  OPENCLAW1PWD
# =============================================================================

set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────────────
G="\033[32m"; Y="\033[33m"; R="\033[31m"; B="\033[34m"; C="\033[36m"; N="\033[0m"
ok()    { echo -e "${G}[OK]${N}   $*"; }
info()  { echo -e "${B}[..]${N}   $*"; }
warn()  { echo -e "${Y}[!]${N}    $*"; }
fail()  { echo -e "${R}[FAIL]${N} $*"; exit 1; }
hdr()   { echo -e "\n${C}━━━  $*  ━━━${N}"; }
ask()   { echo -e "${Y}[?]${N}    $* [y/N] "; read -r _ANS; [[ "${_ANS,,}" == y* ]]; }

# ── Locate project root ───────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SRC="${PROJECT}/src"

# ── Defaults ─────────────────────────────────────────────────────────────────
TARGET="ts2"
YES=false
NO_BACKUP=false
NO_TESTS=false
FORCE_RESTART=false
TARIS_HOME="${HOME}/.taris"
TARIS_USER="${USER}"
TS2_SERVICES=(taris-telegram taris-web)

# ── Arg parsing ───────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)      TARGET="$2"; shift 2 ;;
    --yes|-y)      YES=true; shift ;;
    --no-backup)   NO_BACKUP=true; shift ;;
    --no-tests)    NO_TESTS=true; shift ;;
    --force-restart) FORCE_RESTART=true; shift ;;
    -h|--help)
      sed -n '2,30p' "${BASH_SOURCE[0]}" | grep '^#' | sed 's/^# *//'
      exit 0 ;;
    *) warn "Unknown option: $1"; shift ;;
  esac
done

[[ "$TARGET" != "ts2" && "$TARGET" != "ts1" ]] && \
  fail "Invalid --target '$TARGET'. Use: ts2 (local) or ts1 (remote SintAItion)"

# ── Load .env for TS1 credentials ────────────────────────────────────────────
ENV_FILE="${PROJECT}/.env"
if [[ "$TARGET" == "ts1" ]]; then
  [[ -f "$ENV_FILE" ]] || fail "No .env file at ${PROJECT}/.env (needed for ts1 SSH creds)"
  # shellcheck disable=SC1090
  source <(grep -E '^(OPENCLAW1_HOST|OPENCLAW1_USER|OPENCLAW1PWD)=' "$ENV_FILE")
  OPENCLAW1_HOST="${OPENCLAW1_HOST:-SintAItion}"
  OPENCLAW1_USER="${OPENCLAW1_USER:-stas}"
  [[ -z "${OPENCLAW1PWD:-}" ]] && fail "OPENCLAW1PWD not set in .env"
fi

# ── Version detection ─────────────────────────────────────────────────────────
DEPLOYED_VER=""
SRC_VER=$(grep 'BOT_VERSION' "${SRC}/core/bot_config.py" 2>/dev/null | head -1 | cut -d'"' -f2 || echo "?")

if [[ "$TARGET" == "ts2" ]]; then
  DEPLOYED_VER=$(grep 'BOT_VERSION' "${TARIS_HOME}/core/bot_config.py" 2>/dev/null | head -1 | cut -d'"' -f2 || echo "not installed")
else
  DEPLOYED_VER=$(sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no \
    "${OPENCLAW1_USER}@${OPENCLAW1_HOST}" \
    "grep BOT_VERSION ~/.taris/core/bot_config.py 2>/dev/null | head -1 | cut -d'\"' -f2" 2>/dev/null || echo "?")
fi

# ── Header ────────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║      Taris Bot — OpenClaw Update / Deploy               ║"
echo "╚══════════════════════════════════════════════════════════╝"
if [[ "$TARGET" == "ts2" ]]; then
  echo "  Target   : TariStation2 (local — ${TARIS_HOME})"
else
  echo "  Target   : TariStation1 / SintAItion (${OPENCLAW1_HOST})"
fi
echo "  Source   : ${SRC_VER}"
echo "  Deployed : ${DEPLOYED_VER}"
echo "  Project  : ${PROJECT}"
echo ""

# ── Confirmation ──────────────────────────────────────────────────────────────
if [[ "$YES" == false ]]; then
  if [[ "$TARGET" == "ts1" ]]; then
    echo -e "${R}  ⚠  PRODUCTION TARGET — TariStation1 (SintAItion)${N}"
    echo "  Only deploy here after TariStation2 has been tested!"
    echo ""
  fi
  ask "Proceed with deployment to ${TARGET}?" || { echo "Aborted."; exit 0; }
fi

# ── Helpers for remote execution ──────────────────────────────────────────────
_remote() { sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no \
              "${OPENCLAW1_USER}@${OPENCLAW1_HOST}" "$@"; }
_scp()    { sshpass -p "$OPENCLAW1PWD" scp -o StrictHostKeyChecking=no -r "$@"; }

# ── Step 0.5: Backup ──────────────────────────────────────────────────────────
hdr "Step 1/7 — Pre-deploy backup"
if [[ "$NO_BACKUP" == true ]]; then
  warn "Skipping backup (--no-backup)"
else
  TS=$(date +%Y%m%d_%H%M%S)
  BNAME="taris_backup_${TARGET}_v${DEPLOYED_VER}_${TS}"
  BACKUP_LOCAL="${PROJECT}/backup/snapshots/${BNAME}"
  mkdir -p "$BACKUP_LOCAL"

  if [[ "$TARGET" == "ts2" ]]; then
    tar czf "/tmp/${BNAME}.tar.gz" \
      -C "${TARIS_HOME}" \
      --exclude='vosk-model-*' --exclude='*.onnx' --exclude='ggml-*.bin' \
      --exclude='*/__pycache__' --exclude='*.pyc' \
      . 2>/dev/null
    cp "/tmp/${BNAME}.tar.gz" "${BACKUP_LOCAL}/"
    rm "/tmp/${BNAME}.tar.gz"
  else
    _remote "tar czf /tmp/${BNAME}.tar.gz \
      -C ~/.taris \
      --exclude='vosk-model-*' --exclude='*.onnx' --exclude='ggml-*.bin' \
      --exclude='*/__pycache__' --exclude='*.pyc' \
      . 2>/dev/null && echo BACKUP_OK"
    _scp "${OPENCLAW1_USER}@${OPENCLAW1_HOST}:/tmp/${BNAME}.tar.gz" "${BACKUP_LOCAL}/"
    _remote "rm /tmp/${BNAME}.tar.gz"
  fi

  BACKUP_SIZE=$(du -sh "${BACKUP_LOCAL}/${BNAME}.tar.gz" 2>/dev/null | cut -f1 || echo "?")
  ok "Backup saved: backup/snapshots/${BNAME}/ (${BACKUP_SIZE})"

  # Keep only last 3 backups
  ls -dt "${PROJECT}/backup/snapshots/taris_backup_${TARGET}_"* 2>/dev/null | \
    tail -n +4 | xargs rm -rf 2>/dev/null || true
fi

# ── Step 0.6: Data directory check ───────────────────────────────────────────
hdr "Step 2/7 — Data directory check"
_check_data_dirs() {
  local missing=()
  for d in calendar notes contacts screens web/templates web/static; do
    [[ -d "${TARIS_HOME}/${d}" ]] || missing+=("$d")
  done
  for f in taris.db bot.env; do
    [[ -f "${TARIS_HOME}/${f}" ]] || missing+=("$f")
  done
  if [[ ${#missing[@]} -gt 0 ]]; then
    warn "Missing data paths: ${missing[*]}"
    warn "This may be a first-time install — run install_openclaw.sh instead"
    if [[ "$YES" == false ]]; then
      ask "Continue anyway?" || { echo "Aborted."; exit 1; }
    fi
  else
    ok "All data dirs present"
  fi
}

if [[ "$TARGET" == "ts2" ]]; then
  _check_data_dirs
else
  DATA_CHECK=$(_remote "
    missing=()
    for d in calendar notes contacts screens web/templates web/static; do
      [[ -d ~/.taris/\$d ]] || missing+=(\"\$d\")
    done
    for f in taris.db bot.env; do
      [[ -f ~/.taris/\$f ]] || missing+=(\"\$f\")
    done
    if [[ \${#missing[@]} -gt 0 ]]; then
      echo \"MISSING: \${missing[*]}\"
    else
      echo OK
    fi
  " 2>/dev/null)
  if [[ "$DATA_CHECK" == OK ]]; then
    ok "All data dirs present on ${OPENCLAW1_HOST}"
  else
    warn "On ${OPENCLAW1_HOST}: ${DATA_CHECK}"
    if [[ "$YES" == false ]]; then
      ask "Continue anyway?" || { echo "Aborted."; exit 1; }
    fi
  fi
fi

# ── Step 1: Deploy files ──────────────────────────────────────────────────────
hdr "Step 3/7 — Deploy source files"

if [[ "$TARGET" == "ts2" ]]; then
  # Ensure package dirs exist with __init__.py
  for pkg in core telegram features ui security; do
    mkdir -p "${TARIS_HOME}/${pkg}"
    touch "${TARIS_HOME}/${pkg}/__init__.py"
  done
  mkdir -p "${TARIS_HOME}/tests/voice/results" \
           "${TARIS_HOME}/screens" \
           "${TARIS_HOME}/web/templates" \
           "${TARIS_HOME}/web/static"

  # Python packages
  for pkg in core telegram features ui security; do
    [[ -d "${SRC}/${pkg}" ]] && cp "${SRC}/${pkg}/"*.py "${TARIS_HOME}/${pkg}/" && \
      info "  ${pkg}/*.py"
  done
  # Entry points
  for f in bot_web.py telegram_menu_bot.py voice_assistant.py gmail_digest.py; do
    [[ -f "${SRC}/${f}" ]] && cp "${SRC}/${f}" "${TARIS_HOME}/${f}" && info "  ${f}"
  done
  # Data files
  cp "${SRC}/strings.json" "${SRC}/release_notes.json" "${TARIS_HOME}/"
  info "  strings.json release_notes.json"
  # Screens
  [[ -d "${SRC}/screens" ]] && cp "${SRC}/screens/"*.yaml "${TARIS_HOME}/screens/" 2>/dev/null || true
  [[ -f "${SRC}/screens/screen.schema.json" ]] && \
    cp "${SRC}/screens/screen.schema.json" "${TARIS_HOME}/screens/"
  info "  screens/*.yaml"
  # Web
  cp -r "${SRC}/web/templates/." "${TARIS_HOME}/web/templates/"
  cp -r "${SRC}/web/static/." "${TARIS_HOME}/web/static/"
  info "  web/templates/* web/static/*"
  # Tests
  [[ -d "${SRC}/tests" ]] && \
    { mkdir -p "${TARIS_HOME}/tests"; cp -r "${SRC}/tests/." "${TARIS_HOME}/tests/"; info "  tests/"; }

  ok "All files deployed to ${TARIS_HOME}"

else
  # Remote TariStation1
  _remote "
    for pkg in core telegram features ui security; do
      mkdir -p ~/.taris/\$pkg
      touch ~/.taris/\$pkg/__init__.py
    done
    mkdir -p ~/.taris/tests/voice/results ~/.taris/screens ~/.taris/web/templates ~/.taris/web/static
  "
  for pkg in core telegram features ui security; do
    [[ -d "${SRC}/${pkg}" ]] && _scp "${SRC}/${pkg}/"*.py \
      "${OPENCLAW1_USER}@${OPENCLAW1_HOST}:~/.taris/${pkg}/" && info "  ${pkg}/*.py"
  done
  _scp "${SRC}/bot_web.py" "${SRC}/telegram_menu_bot.py" \
       "${SRC}/voice_assistant.py" "${SRC}/gmail_digest.py" \
       "${OPENCLAW1_USER}@${OPENCLAW1_HOST}:~/.taris/"
  _scp "${SRC}/strings.json" "${SRC}/release_notes.json" \
       "${OPENCLAW1_USER}@${OPENCLAW1_HOST}:~/.taris/"
  [[ -d "${SRC}/screens" ]] && \
    _scp "${SRC}/screens/" "${OPENCLAW1_USER}@${OPENCLAW1_HOST}:~/.taris/"
  _scp "${SRC}/web/templates/" "${SRC}/web/static/" \
       "${OPENCLAW1_USER}@${OPENCLAW1_HOST}:~/.taris/web/"
  [[ -d "${SRC}/tests" ]] && \
    _scp "${SRC}/tests/" "${OPENCLAW1_USER}@${OPENCLAW1_HOST}:~/.taris/"
  ok "All files deployed to ${OPENCLAW1_HOST}"
fi

# ── Sync verification (local only) ───────────────────────────────────────────
if [[ "$TARGET" == "ts2" ]]; then
  SYNC_FAIL=()
  for f in src/bot_web.py src/core/bot_config.py src/core/bot_llm.py src/ui/bot_ui.py; do
    diff "${PROJECT}/${f}" "${TARIS_HOME}/${f#src/}" >/dev/null 2>&1 || SYNC_FAIL+=("$f")
  done
  if [[ ${#SYNC_FAIL[@]} -gt 0 ]]; then
    warn "Sync mismatch detected for: ${SYNC_FAIL[*]}"
    fail "Deploy verification failed — services NOT restarted"
  fi
  ok "Sync verified"
fi

# ── Service file update ───────────────────────────────────────────────────────
hdr "Step 4/7 — Service files"
SVC_UPDATED=false
if [[ "$TARGET" == "ts2" ]]; then
  SVC_DEST="${HOME}/.config/systemd/user"
  mkdir -p "$SVC_DEST"
  for svc in taris-telegram taris-web taris-voice; do
    SVC_SRC="${SRC}/services/${svc}.service"
    SVC_DST="${SVC_DEST}/${svc}.service"
    [[ -f "$SVC_SRC" ]] || continue
    if ! cmp -s "$SVC_SRC" "$SVC_DST" 2>/dev/null; then
      cp "$SVC_SRC" "$SVC_DST"
      SVC_UPDATED=true
      info "  Updated service: ${svc}.service"
    fi
  done
  if [[ "$SVC_UPDATED" == true ]]; then
    systemctl --user daemon-reload
    ok "Service files updated, daemon reloaded"
  else
    ok "Service files unchanged"
  fi
else
  for svc in taris-telegram taris-web; do
    SVC_SRC="${SRC}/services/${svc}.service"
    [[ -f "$SVC_SRC" ]] || continue
    _scp "$SVC_SRC" "${OPENCLAW1_USER}@${OPENCLAW1_HOST}:/tmp/${svc}.service"
    _remote "
      if ! cmp -s /tmp/${svc}.service ~/.config/systemd/user/${svc}.service 2>/dev/null; then
        mkdir -p ~/.config/systemd/user
        cp /tmp/${svc}.service ~/.config/systemd/user/${svc}.service
        echo UPDATED
      fi
      rm -f /tmp/${svc}.service
    " | grep -q UPDATED && SVC_UPDATED=true || true
  done
  if [[ "$SVC_UPDATED" == true ]]; then
    _remote "systemctl --user daemon-reload"
    ok "Service files updated on ${OPENCLAW1_HOST}"
  else
    ok "Service files unchanged"
  fi
fi

# ── Step: Restart services ───────────────────────────────────────────────────
hdr "Step 5/7 — Restart services"
if [[ "$TARGET" == "ts2" ]]; then
  ACTIVE_SVCS=()
  for svc in "${TS2_SERVICES[@]}"; do
    systemctl --user is-active --quiet "$svc" 2>/dev/null && ACTIVE_SVCS+=("$svc") || true
  done
  if [[ ${#ACTIVE_SVCS[@]} -eq 0 ]]; then
    warn "No active taris services found — starting taris-telegram taris-web"
    systemctl --user start taris-telegram taris-web || true
    ACTIVE_SVCS=(taris-telegram taris-web)
  else
    systemctl --user restart "${ACTIVE_SVCS[@]}"
  fi
  ok "Restarted: ${ACTIVE_SVCS[*]}"
  sleep 5
else
  _remote "systemctl --user restart taris-telegram taris-web 2>/dev/null; sleep 5"
  ok "Services restarted on ${OPENCLAW1_HOST}"
fi

# ── Step: Verify journal ─────────────────────────────────────────────────────
hdr "Step 6/7 — Verify startup"
JOURNAL_OK=true
if [[ "$TARGET" == "ts2" ]]; then
  JLOG=$(journalctl --user -u taris-telegram -n 20 --no-pager 2>/dev/null)
  echo "$JLOG" | tail -10
  echo "$JLOG" | grep -q "Polling Telegram" || JOURNAL_OK=false
  echo "$JLOG" | grep -qi "error\|exception\|traceback" && JOURNAL_OK=false || true
else
  JLOG=$(_remote "journalctl --user -u taris-telegram -n 20 --no-pager 2>/dev/null")
  echo "$JLOG" | tail -10
  echo "$JLOG" | grep -q "Polling Telegram" || JOURNAL_OK=false
fi

if [[ "$JOURNAL_OK" == true ]]; then
  ok "Service started and polling Telegram ✓"
else
  fail "Service did NOT reach 'Polling Telegram' state — check logs above"
fi

# ── Step: Smoke tests ────────────────────────────────────────────────────────
hdr "Step 7/7 — Smoke tests"
if [[ "$NO_TESTS" == true ]]; then
  warn "Skipping smoke tests (--no-tests)"
else
  SMOKE_TESTS="t_openclaw_stt_routing t_openclaw_ollama_provider i18n_string_coverage bot_name_injection"
  SMOKE_CMD="DEVICE_VARIANT=openclaw PYTHONPATH=~/.taris python3 ~/.taris/tests/test_voice_regression.py --test ${SMOKE_TESTS}"

  if [[ "$TARGET" == "ts2" ]]; then
    TARS_HOME="${TARIS_HOME}"
    SMOKE_RESULT=$(DEVICE_VARIANT=openclaw PYTHONPATH="${TARS_HOME}" \
      python3 "${TARS_HOME}/tests/test_voice_regression.py" \
      --test t_openclaw_stt_routing t_openclaw_ollama_provider i18n_string_coverage bot_name_injection \
      2>&1 | tail -5)
  else
    SMOKE_RESULT=$(_remote "${SMOKE_CMD}" 2>&1 | tail -5)
  fi

  echo "$SMOKE_RESULT"
  if echo "$SMOKE_RESULT" | grep -q "FAIL"; then
    warn "Some smoke tests FAILED — review output above"
  else
    ok "Smoke tests passed ✓"
  fi
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║                 Deployment Summary                      ║"
echo "╚══════════════════════════════════════════════════════════╝"
if [[ "$TARGET" == "ts2" ]]; then
  DEPLOYED_NEW=$(grep 'BOT_VERSION' "${TARIS_HOME}/core/bot_config.py" 2>/dev/null | head -1 | cut -d'"' -f2 || echo "?")
  echo "  Target  : TariStation2 (local)"
  echo "  Version : ${DEPLOYED_VER} → ${DEPLOYED_NEW}"
  if [[ "$NO_BACKUP" == false ]]; then
    echo "  Backup  : backup/snapshots/${BNAME:-none}/"
  fi
  echo ""
  echo "  Next steps:"
  echo "    1. Test the bot in Telegram"
  echo "    2. Run full regression: DEVICE_VARIANT=openclaw PYTHONPATH=~/.taris \\"
  echo "         python3 src/tests/test_voice_regression.py"
  echo "    3. Deploy to TariStation1? (requires explicit confirmation)"
  echo "         bash src/setup/update_openclaw.sh --target ts1"
else
  echo "  Target  : TariStation1 / SintAItion (${OPENCLAW1_HOST})"
  echo "  Version : ${DEPLOYED_VER} → ${SRC_VER}"
  echo ""
  echo -e "  ${G}TariStation1 deployed and verified ✅${N}"
fi
echo ""
