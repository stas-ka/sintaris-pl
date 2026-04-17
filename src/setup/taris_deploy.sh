#!/usr/bin/env bash
# =============================================================================
# taris_deploy.sh — Unified Taris Deployment, Backup, Migration & Install Tool
# =============================================================================
# Single entry point for all deployment operations across all targets/variants.
# Called by skills; mandatory rules (target order, branch rules, confirmations)
# are enforced by the SKILL.md files, NOT by this script.
#
# Usage:
#   bash src/setup/taris_deploy.sh --action ACTION --target TARGET [OPTIONS]
#
# Actions:
#   deploy      Deploy source files to target (default)
#   backup      Backup data/software/system/binaries on target
#   patch       Deploy specific files only (--files list)
#   migrate     Run data migration (migrate_to_db.py) on target
#   install     Full installation incl. third-party packages + service setup
#   restart     Restart services only
#   verify      Check service status + journal tail + version
#
# Targets:
#   vps   VPS staging (dev2null.de, Docker, any branch — default for feature branches)
#   ts2   TariStation2 (local OpenClaw, engineering)
#   ts1   TariStation1 / SintAItion (remote OpenClaw, production)
#   pi2   OpenClawPI2 (remote PicoClaw, engineering)
#   pi1   OpenClawPI (remote PicoClaw, production)
#
# Variant (auto-detected from target; override if needed):
#   openclaw   ts1, ts2, vps — user systemd or Docker, cp or sshpass scp
#   picoclaw   pi1, pi2 — system systemd (sudo), sshpass scp
#
# Options:
#   --action ACTION         backup|deploy|patch|migrate|install|restart|verify
#   --target TARGET         vps|ts2|ts1|pi2|pi1
#   --variant VARIANT       openclaw|picoclaw (auto-detected if not given)
#   --backup-type TYPE      data|software|system|binaries|all  (backup action)
#   --files FILE1,FILE2     Comma-sep src/-relative paths for patch action
#   --git-ref REF           git commit/tag/branch to check out before deploy
#   --host HOSTNAME         Override target hostname
#   --user USERNAME         Override SSH username
#   --password PWD          Override SSH password (avoid: use .env or .credentials)
#   --taris-home PATH       Override deploy path (default: ~/.taris)
#   --yes / -y              Non-interactive (skip confirmation prompts)
#   --no-backup             Skip pre-deploy backup
#   --no-tests              Skip post-deploy smoke tests
#   --no-migrate            Skip migration step during deploy
#   --force-restart         Restart services even if no file change detected
#   --upgrade-binary        Upgrade picoclaw/openclaw binary during install/deploy
#   -h, --help              Show this help text
# =============================================================================

set -euo pipefail

# ── Colours ───────────────────────────────────────────────────────────────────
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

# ── Defaults ──────────────────────────────────────────────────────────────────
ACTION="deploy"
TARGET=""
VARIANT=""
BACKUP_TYPE="data"
PATCH_FILES=""
GIT_REF=""
OPT_HOST=""
OPT_USER=""
OPT_PASSWORD=""
OPT_TARIS_HOME=""
YES=false
NO_BACKUP=false
NO_TESTS=false
NO_MIGRATE=false
FORCE_RESTART=false
UPGRADE_BINARY=false

# ── Arg parsing ───────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --action)          ACTION="$2";         shift 2 ;;
    --target)          TARGET="$2";         shift 2 ;;
    --variant)         VARIANT="$2";        shift 2 ;;
    --backup-type)     BACKUP_TYPE="$2";    shift 2 ;;
    --files)           PATCH_FILES="$2";    shift 2 ;;
    --git-ref)         GIT_REF="$2";        shift 2 ;;
    --host)            OPT_HOST="$2";       shift 2 ;;
    --user)            OPT_USER="$2";       shift 2 ;;
    --password)        OPT_PASSWORD="$2";   shift 2 ;;
    --taris-home)      OPT_TARIS_HOME="$2"; shift 2 ;;
    --yes|-y)          YES=true;            shift ;;
    --no-backup)       NO_BACKUP=true;      shift ;;
    --no-tests)        NO_TESTS=true;       shift ;;
    --no-migrate)      NO_MIGRATE=true;     shift ;;
    --force-restart)   FORCE_RESTART=true;  shift ;;
    --upgrade-binary)  UPGRADE_BINARY=true; shift ;;
    -h|--help)
      sed -n '6,60p' "${BASH_SOURCE[0]}" | grep '^#' | sed 's/^# *//'
      exit 0 ;;
    *) warn "Unknown option: $1"; shift ;;
  esac
done

# ── Validate action ───────────────────────────────────────────────────────────
case "$ACTION" in
  deploy|backup|patch|migrate|install|restart|verify) ;;
  *) fail "Unknown --action '${ACTION}'. Valid: deploy backup patch migrate install restart verify" ;;
esac

# ── Validate target ───────────────────────────────────────────────────────────
[[ -z "$TARGET" ]] && fail "--target is required. Valid: vps ts2 ts1 pi2 pi1"
case "$TARGET" in
  vps|ts2|ts1|pi2|pi1) ;;
  *) fail "Unknown --target '${TARGET}'. Valid: vps ts2 ts1 pi2 pi1" ;;
esac

# ── Patch action requires --files ─────────────────────────────────────────────
[[ "$ACTION" == "patch" && -z "$PATCH_FILES" ]] && \
  fail "--action patch requires --files FILE1,FILE2,..."

# ── Auto-detect variant ───────────────────────────────────────────────────────
if [[ -z "$VARIANT" ]]; then
  case "$TARGET" in
    ts1|ts2|vps) VARIANT="openclaw" ;;
    pi1|pi2) VARIANT="picoclaw" ;;
  esac
fi

# ── Validate variant ──────────────────────────────────────────────────────────
case "$VARIANT" in
  openclaw|picoclaw) ;;
  *) fail "Unknown --variant '${VARIANT}'. Valid: openclaw picoclaw" ;;
esac

# =============================================================================
# TARGET CONFIGURATION
# =============================================================================
IS_LOCAL=false
IS_DOCKER=false
REMOTE_HOST=""
REMOTE_USER="stas"
REMOTE_PASS=""
TARIS_HOME="${OPT_TARIS_HOME:-/home/stas/.taris}"

# Load .env for remote credentials
ENV_FILE="${PROJECT}/.env"
CREDS_FILE="${PROJECT}/.credentials/.taris_env"

_load_cred() {
  # _load_cred KEY1 KEY2 ... → first non-empty value from .env/.credentials
  local val=""
  for _f in "$CREDS_FILE" "$ENV_FILE"; do
    [[ -f "$_f" ]] || continue
    for _k in "$@"; do
      val=$(grep -E "^${_k}=" "$_f" 2>/dev/null | head -1 | cut -d'=' -f2- | tr -d '"' || true)
      [[ -n "$val" ]] && echo "$val" && return
    done
  done
  echo ""
}

case "$TARGET" in
  vps)
    IS_LOCAL=false
    IS_DOCKER=true
    REMOTE_HOST="${OPT_HOST:-$(_load_cred VPS_HOST)}"
    REMOTE_HOST="${REMOTE_HOST:-dev2null.de}"
    REMOTE_USER="${OPT_USER:-$(_load_cred VPS_USER)}"
    REMOTE_USER="${REMOTE_USER:-stas}"
    REMOTE_PASS="${OPT_PASSWORD:-$(_load_cred VPS_PWD)}"
    TARIS_HOME="${OPT_TARIS_HOME:-/opt/taris-docker/app/src}"
    DOCKER_DATA_HOME="/opt/taris-docker"
    DOCKER_CONTAINERS=(taris-vps-telegram taris-vps-web)
    SERVICES=(taris-vps-telegram taris-vps-web)
    DEVICE_VARIANT="openclaw"
    SMOKE_TESTS="t_openclaw_stt_routing i18n_string_coverage bot_name_injection"
    ;;
  ts2)
    IS_LOCAL=true
    TARIS_HOME="${OPT_TARIS_HOME:-${HOME}/.taris}"
    SYSTEMCTL_SVC="systemctl --user"
    SVC_DIR="${HOME}/.config/systemd/user"
    SERVICES=(taris-telegram taris-web)
    DEVICE_VARIANT="openclaw"
    SMOKE_TESTS="t_openclaw_stt_routing t_openclaw_ollama_provider i18n_string_coverage bot_name_injection"
    ;;
  ts1)
    IS_LOCAL=false
    REMOTE_HOST="${OPT_HOST:-$(_load_cred OPENCLAW1_HOST)}"
    REMOTE_HOST="${REMOTE_HOST:-SintAItion}"
    REMOTE_USER="${OPT_USER:-$(_load_cred OPENCLAW1_USER)}"
    REMOTE_USER="${REMOTE_USER:-stas}"
    REMOTE_PASS="${OPT_PASSWORD:-$(_load_cred OPENCLAW1PWD)}"
    TARIS_HOME="${OPT_TARIS_HOME:-/home/${REMOTE_USER}/.taris}"
    SYSTEMCTL_SVC="systemctl --user"
    SVC_DIR="${HOME}/.config/systemd/user"   # set properly in _exec
    SVC_DIR_REMOTE="/home/${REMOTE_USER}/.config/systemd/user"
    SERVICES=(taris-telegram taris-web)
    DEVICE_VARIANT="openclaw"
    SMOKE_TESTS="t_openclaw_stt_routing t_openclaw_ollama_provider i18n_string_coverage bot_name_injection"
    ;;
  pi2)
    IS_LOCAL=false
    REMOTE_HOST="${OPT_HOST:-$(_load_cred DEV_HOST)}"
    [[ -n "$REMOTE_HOST" ]] && REMOTE_HOST="${REMOTE_HOST}.local" || REMOTE_HOST="OpenClawPI2.local"
    REMOTE_HOST="${OPT_HOST:-$REMOTE_HOST}"
    REMOTE_USER="${OPT_USER:-stas}"
    REMOTE_PASS="${OPT_PASSWORD:-$(_load_cred DEV_HOSTPWD DEV_HOST_PWD)}"
    TARIS_HOME="${OPT_TARIS_HOME:-/home/stas/.taris}"
    SYSTEMCTL_SVC="sudo systemctl"
    SVC_DIR="/etc/systemd/system"
    SERVICES=(taris-telegram taris-web)
    DEVICE_VARIANT="picoclaw"
    SMOKE_TESTS="model_files_present i18n_string_coverage bot_name_injection note_edit_append_replace"
    ;;
  pi1)
    IS_LOCAL=false
    REMOTE_HOST="${OPT_HOST:-$(_load_cred PROD_HOST)}"
    [[ -n "$REMOTE_HOST" ]] && REMOTE_HOST="${REMOTE_HOST}.local" || REMOTE_HOST="OpenClawPI.local"
    REMOTE_HOST="${OPT_HOST:-$REMOTE_HOST}"
    REMOTE_USER="${OPT_USER:-stas}"
    REMOTE_PASS="${OPT_PASSWORD:-$(_load_cred PROD_HOSTPWD PROD_HOST_PWD)}"
    TARIS_HOME="${OPT_TARIS_HOME:-/home/stas/.taris}"
    SYSTEMCTL_SVC="sudo systemctl"
    SVC_DIR="/etc/systemd/system"
    SERVICES=(taris-telegram taris-web)
    DEVICE_VARIANT="picoclaw"
    SMOKE_TESTS="model_files_present i18n_string_coverage bot_name_injection note_edit_append_replace"
    ;;
esac

# Check password for remote targets
if [[ "$IS_LOCAL" == false && -z "$REMOTE_PASS" ]]; then
  printf "${Y}[?]${N}    Enter SSH password for ${REMOTE_USER}@${REMOTE_HOST}: "
  read -rs REMOTE_PASS; echo ""
  [[ -z "$REMOTE_PASS" ]] && fail "SSH password required for remote target ${TARGET}"
fi

# Check sshpass for remote
if [[ "$IS_LOCAL" == false ]]; then
  command -v sshpass >/dev/null 2>&1 || fail "sshpass not installed. Run: sudo apt-get install sshpass"
fi

# =============================================================================
# TRANSPORT HELPERS
# =============================================================================

# _exec CMD — run command locally or on remote target
_exec() {
  if [[ "$IS_LOCAL" == true ]]; then
    bash -c "$*"
  else
    sshpass -p "$REMOTE_PASS" ssh \
      -o StrictHostKeyChecking=no -o ConnectTimeout=15 \
      "${REMOTE_USER}@${REMOTE_HOST}" "$@"
  fi
}

# _exec_sudo CMD — run command with sudo (picoclaw: ssh sudo; openclaw: local sudo or user)
_exec_sudo() {
  if [[ "$IS_LOCAL" == true ]]; then
    # openclaw ts2: services run as user, no sudo needed for systemctl --user
    bash -c "$*"
  elif [[ "$VARIANT" == "picoclaw" ]]; then
    sshpass -p "$REMOTE_PASS" ssh \
      -o StrictHostKeyChecking=no -o ConnectTimeout=15 \
      "${REMOTE_USER}@${REMOTE_HOST}" "echo '$REMOTE_PASS' | sudo -S $*"
  else
    sshpass -p "$REMOTE_PASS" ssh \
      -o StrictHostKeyChecking=no -o ConnectTimeout=15 \
      "${REMOTE_USER}@${REMOTE_HOST}" "$@"
  fi
}

# _cp SRC DEST — copy local file(s) to target path
_cp() {
  local src="$1" dest="$2"
  if [[ "$IS_LOCAL" == true ]]; then
    cp -r "$src" "$dest"
  else
    sshpass -p "$REMOTE_PASS" scp \
      -o StrictHostKeyChecking=no -r \
      "$src" "${REMOTE_USER}@${REMOTE_HOST}:${dest}"
  fi
}

# _cp_many SRC_GLOB DEST_DIR — copy multiple files to dest directory
_cp_many() {
  local glob="$1" dest="$2"
  local files
  # shellcheck disable=SC2206
  files=($glob)
  [[ ${#files[@]} -eq 0 ]] && return
  if [[ "$IS_LOCAL" == true ]]; then
    cp -r "${files[@]}" "$dest/"
  else
    sshpass -p "$REMOTE_PASS" scp \
      -o StrictHostKeyChecking=no -r \
      "${files[@]}" "${REMOTE_USER}@${REMOTE_HOST}:${dest}/"
  fi
}

# _mkdir_p PATH — ensure directory exists on target
_mkdir_p() {
  _exec "mkdir -p '$1'" 2>/dev/null || true
}

# _svc_ctl ACTION SERVICE... — run systemctl on target
_svc_ctl() {
  local action="$1"; shift
  if [[ "$IS_LOCAL" == true ]]; then
    systemctl --user "$action" "$@" 2>/dev/null || true
  elif [[ "$VARIANT" == "picoclaw" ]]; then
    sshpass -p "$REMOTE_PASS" ssh \
      -o StrictHostKeyChecking=no -o ConnectTimeout=15 \
      "${REMOTE_USER}@${REMOTE_HOST}" \
      "echo '$REMOTE_PASS' | sudo -S systemctl $action $*" 2>/dev/null || true
  else
    sshpass -p "$REMOTE_PASS" ssh \
      -o StrictHostKeyChecking=no -o ConnectTimeout=15 \
      "${REMOTE_USER}@${REMOTE_HOST}" \
      "systemctl --user $action $*" 2>/dev/null || true
  fi
}

# _daemon_reload — daemon-reload on target
_daemon_reload() {
  if [[ "$IS_LOCAL" == true ]]; then
    systemctl --user daemon-reload 2>/dev/null || true
  elif [[ "$VARIANT" == "picoclaw" ]]; then
    _exec_sudo "systemctl daemon-reload"
  else
    _exec "systemctl --user daemon-reload"
  fi
}

# _get_version — get BOT_VERSION from deployed target
_get_version() {
  if [[ "$IS_DOCKER" == true ]]; then
    _exec "docker exec ${DOCKER_CONTAINERS[0]} python3 -c 'from core.bot_config import BOT_VERSION; print(BOT_VERSION)' 2>/dev/null" || \
    _exec "grep BOT_VERSION ${TARIS_HOME}/core/bot_config.py 2>/dev/null | head -1 | cut -d'\"' -f2" 2>/dev/null || echo "?"
  else
    _exec "grep BOT_VERSION ${TARIS_HOME}/core/bot_config.py 2>/dev/null | head -1 | cut -d'\"' -f2" 2>/dev/null || echo "?"
  fi
}

# _get_src_version — get BOT_VERSION from source
_get_src_version() {
  grep 'BOT_VERSION' "${SRC}/core/bot_config.py" 2>/dev/null | head -1 | cut -d'"' -f2 || echo "?"
}

# =============================================================================
# CONNECTIVITY CHECK
# =============================================================================
_check_connectivity() {
  if [[ "$IS_LOCAL" == false ]]; then
    hdr "Connectivity"
    _exec "echo connected" >/dev/null 2>&1 || \
      fail "Cannot reach ${REMOTE_USER}@${REMOTE_HOST} — check hostname/password"
    ok "Connected to ${REMOTE_HOST}"
  fi
}

# =============================================================================
# VERSION INFO
# =============================================================================
SRC_VER=""
DEPLOYED_VER=""

_detect_versions() {
  SRC_VER="$(_get_src_version)"
  DEPLOYED_VER="$(_get_version 2>/dev/null || echo 'not installed')"
}

# =============================================================================
# HEADER
# =============================================================================
_print_header() {
  echo ""
  echo "╔══════════════════════════════════════════════════════════╗"
  echo "║           Taris Deploy Tool — ${ACTION^^}$(printf '%*s' $((22-${#ACTION})) '')║"
  echo "╚══════════════════════════════════════════════════════════╝"
  printf "  %-12s %s\n" "Action:"   "$ACTION"
  printf "  %-12s %s\n" "Target:"   "$TARGET"
  printf "  %-12s %s\n" "Variant:"  "$VARIANT"
  if [[ "$IS_LOCAL" == true ]]; then
    printf "  %-12s %s\n" "Host:"     "local (${TARIS_HOME})"
  else
    printf "  %-12s %s\n" "Host:"     "${REMOTE_USER}@${REMOTE_HOST}"
    printf "  %-12s %s\n" "Deploy:"   "${TARIS_HOME}"
  fi
  if [[ -n "$SRC_VER" ]]; then
    printf "  %-12s %s\n" "Source:"   "$SRC_VER"
    printf "  %-12s %s\n" "Deployed:" "$DEPLOYED_VER"
  fi
  echo ""
}

# =============================================================================
# CONFIRMATION
# =============================================================================
_confirm() {
  [[ "$YES" == true ]] && return
  if [[ "$TARGET" == "ts1" || "$TARGET" == "pi1" ]]; then
    echo -e "${R}  ⚠  PRODUCTION TARGET (${TARGET} = ${REMOTE_HOST})${N}"
    echo "  This target should only receive validated deployments."
    echo ""
  fi
  ask "Proceed with '${ACTION}' on target '${TARGET}'?" || { echo "Aborted."; exit 2; }
}

# =============================================================================
# ACTION: VERIFY
# =============================================================================
action_verify() {
  hdr "Verify — service status + journal"
  if [[ "$IS_DOCKER" == true ]]; then
    JLOG=$(_exec "docker logs ${DOCKER_CONTAINERS[0]} 2>&1 | tail -20" 2>/dev/null || true)
    _exec "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep taris" 2>/dev/null || true
    echo "$JLOG" | tail -12
  elif [[ "$IS_LOCAL" == true ]]; then
    systemctl --user status taris-telegram --no-pager 2>/dev/null | head -6 || true
    echo ""
    JLOG=$(journalctl --user -u taris-telegram -n 20 --no-pager 2>/dev/null || true)
    echo "$JLOG" | tail -12
  else
    _exec "systemctl --user status taris-telegram --no-pager 2>/dev/null | head -6" 2>/dev/null || \
    _exec "sudo systemctl status taris-telegram --no-pager 2>/dev/null | head -6" 2>/dev/null || true
    echo ""
    if [[ "$VARIANT" == "picoclaw" ]]; then
      JLOG=$(_exec "journalctl -u taris-telegram -n 20 --no-pager 2>/dev/null" || true)
    else
      JLOG=$(_exec "journalctl --user -u taris-telegram -n 20 --no-pager 2>/dev/null" || true)
    fi
    echo "$JLOG" | tail -12
  fi
  if echo "$JLOG" | grep -q "Polling Telegram"; then
    ok "✓ Service is polling Telegram (Version: $(_get_version))"
  else
    warn "Service does not show 'Polling Telegram' — may still be starting"
  fi
}

# =============================================================================
# ACTION: BACKUP
# =============================================================================
action_backup() {
  hdr "Backup — type: ${BACKUP_TYPE}"
  TS=$(date +%Y%m%d_%H%M%S)
  BNAME="taris_backup_${TARGET}_v${DEPLOYED_VER}_${TS}"
  BACKUP_LOCAL="${PROJECT}/backup/snapshots/${BNAME}"
  mkdir -p "$BACKUP_LOCAL"

  case "$BACKUP_TYPE" in
    data|software|system|binaries|all) ;;
    *) fail "Unknown --backup-type '${BACKUP_TYPE}'. Valid: data software system binaries all" ;;
  esac

  # data (always included in 'all')
  if [[ "$BACKUP_TYPE" == "data" || "$BACKUP_TYPE" == "all" ]]; then
    # VPS: data lives in /opt/taris-docker/ (bot.env, registrations.json etc)
    DATA_DIR="${IS_DOCKER:+${DOCKER_DATA_HOME:-/opt/taris-docker}}"
    DATA_DIR="${DATA_DIR:-${TARIS_HOME}}"
    TAR_CMD="tar czf /tmp/${BNAME}_data.tar.gz \
      -C ${DATA_DIR} \
      --exclude='*/__pycache__' --exclude='*.pyc' --exclude='*.onnx' \
      --exclude='*.bin' --exclude='*.log' --exclude='vosk-model-*' \
      $(ls ${DATA_DIR}/*.json ${DATA_DIR}/*.db ${DATA_DIR}/bot.env 2>/dev/null | xargs -I{} basename {} | tr '\n' ' ') \
      2>/dev/null; echo BACKUP_OK"
    _exec "$TAR_CMD" | grep -q BACKUP_OK || fail "Data backup tar failed"
    if [[ "$IS_LOCAL" == true ]]; then
      cp "/tmp/${BNAME}_data.tar.gz" "${BACKUP_LOCAL}/"
      rm -f "/tmp/${BNAME}_data.tar.gz"
    else
      sshpass -p "$REMOTE_PASS" scp -o StrictHostKeyChecking=no \
        "${REMOTE_USER}@${REMOTE_HOST}:/tmp/${BNAME}_data.tar.gz" "${BACKUP_LOCAL}/"
      _exec "rm -f /tmp/${BNAME}_data.tar.gz"
    fi
    ok "Data backup: ${BACKUP_LOCAL}/${BNAME}_data.tar.gz"
  fi

  # software
  if [[ "$BACKUP_TYPE" == "software" || "$BACKUP_TYPE" == "all" ]]; then
    TAR_CMD="tar czf /tmp/${BNAME}_software.tar.gz \
      -C ${TARIS_HOME} \
      --exclude='*/__pycache__' --exclude='*.pyc' \
      \$(ls ${TARIS_HOME}/*.py 2>/dev/null | xargs -I{} basename {}) \
      strings.json release_notes.json \
      core/ telegram/ features/ ui/ security/ web/ setup/ services/ \
      2>/dev/null; echo BACKUP_OK"
    _exec "$TAR_CMD" | grep -q BACKUP_OK || warn "Software backup had warnings"
    if [[ "$IS_LOCAL" == true ]]; then
      cp "/tmp/${BNAME}_software.tar.gz" "${BACKUP_LOCAL}/" 2>/dev/null || true
      rm -f "/tmp/${BNAME}_software.tar.gz"
    else
      sshpass -p "$REMOTE_PASS" scp -o StrictHostKeyChecking=no \
        "${REMOTE_USER}@${REMOTE_HOST}:/tmp/${BNAME}_software.tar.gz" "${BACKUP_LOCAL}/" 2>/dev/null || true
      _exec "rm -f /tmp/${BNAME}_software.tar.gz" || true
    fi
    ok "Software backup: ${BACKUP_LOCAL}/"
  fi

  # system
  if [[ "$BACKUP_TYPE" == "system" || "$BACKUP_TYPE" == "all" ]]; then
    if [[ "$VARIANT" == "picoclaw" ]]; then
      TAR_CMD="tar czf /tmp/${BNAME}_system.tar.gz \
        /etc/systemd/system/taris*.service \
        /etc/systemd/system/taris*.timer \
        /etc/cron.d/ 2>/dev/null; echo BACKUP_OK"
      _exec_sudo "$TAR_CMD" | grep -q BACKUP_OK || warn "System backup had warnings"
    else
      TAR_CMD="tar czf /tmp/${BNAME}_system.tar.gz \
        ~/.config/systemd/user/taris*.service 2>/dev/null; echo BACKUP_OK"
      _exec "$TAR_CMD" | grep -q BACKUP_OK || warn "System backup had warnings"
    fi
    if [[ "$IS_LOCAL" == true ]]; then
      cp "/tmp/${BNAME}_system.tar.gz" "${BACKUP_LOCAL}/" 2>/dev/null || true
      rm -f "/tmp/${BNAME}_system.tar.gz"
    else
      sshpass -p "$REMOTE_PASS" scp -o StrictHostKeyChecking=no \
        "${REMOTE_USER}@${REMOTE_HOST}:/tmp/${BNAME}_system.tar.gz" "${BACKUP_LOCAL}/" 2>/dev/null || true
      _exec "rm -f /tmp/${BNAME}_system.tar.gz" || true
    fi
    ok "System backup: ${BACKUP_LOCAL}/"
  fi

  # binaries
  if [[ "$BACKUP_TYPE" == "binaries" || "$BACKUP_TYPE" == "all" ]]; then
    BIN_CMD="{ echo '=== pip3 freeze ==='; pip3 freeze 2>/dev/null; \
      echo '=== dpkg ==='; \
      dpkg -l 2>/dev/null | grep -E 'python3|piper|vosk|ffmpeg|libopus|zram|sqlite'; \
      echo '=== binary ==='; \
      picoclaw version 2>/dev/null || openclaw --version 2>/dev/null || echo 'n/a'; \
    } > /tmp/${BNAME}_binaries.txt 2>/dev/null; echo BACKUP_OK"
    _exec "$BIN_CMD" | grep -q BACKUP_OK || warn "Binaries backup had warnings"
    if [[ "$IS_LOCAL" == true ]]; then
      cp "/tmp/${BNAME}_binaries.txt" "${BACKUP_LOCAL}/" 2>/dev/null || true
      rm -f "/tmp/${BNAME}_binaries.txt"
    else
      sshpass -p "$REMOTE_PASS" scp -o StrictHostKeyChecking=no \
        "${REMOTE_USER}@${REMOTE_HOST}:/tmp/${BNAME}_binaries.txt" "${BACKUP_LOCAL}/" 2>/dev/null || true
      _exec "rm -f /tmp/${BNAME}_binaries.txt" || true
    fi
    ok "Binaries list: ${BACKUP_LOCAL}/"
  fi

  BACKUP_SIZE=$(du -sh "${BACKUP_LOCAL}" 2>/dev/null | cut -f1 || echo "?")
  ok "Backup complete: backup/snapshots/${BNAME}/ (${BACKUP_SIZE})"

  # Keep only last 3 backups for this target
  ls -dt "${PROJECT}/backup/snapshots/taris_backup_${TARGET}_"* 2>/dev/null | \
    tail -n +4 | xargs rm -rf 2>/dev/null || true
}

# =============================================================================
# ACTION: MIGRATE
# =============================================================================
action_migrate() {
  hdr "Migrate — run migrate_to_db.py"
  MIGRATE_SCRIPT="${TARIS_HOME}/setup/migrate_to_db.py"
  MIGRATE_CMD="PYTHONPATH=${TARIS_HOME} python3 ${MIGRATE_SCRIPT}"
  if _exec "test -f ${MIGRATE_SCRIPT}" 2>/dev/null; then
    RESULT=$(_exec "$MIGRATE_CMD" 2>&1 | tail -6)
    echo "$RESULT"
    if echo "$RESULT" | grep -qi "error\|traceback"; then
      fail "Migration reported errors — check output above"
    else
      ok "Migration complete"
    fi
  else
    warn "migrate_to_db.py not found at ${MIGRATE_SCRIPT} — skipping"
  fi
}

# =============================================================================
# ACTION: DEPLOY FILE GROUPS
# =============================================================================
_deploy_files() {
  hdr "Deploy source files"

  # Create all required directories on target
  _exec "
    for pkg in core telegram features ui security; do
      mkdir -p ${TARIS_HOME}/\$pkg
      touch ${TARIS_HOME}/\$pkg/__init__.py 2>/dev/null || true
    done
    mkdir -p ${TARIS_HOME}/tests/voice/results \
             ${TARIS_HOME}/screens \
             ${TARIS_HOME}/web/templates \
             ${TARIS_HOME}/web/static \
             ${TARIS_HOME}/setup
  "

  # Python packages
  for pkg in core telegram features ui security; do
    if [[ -d "${SRC}/${pkg}" ]]; then
      if [[ "$IS_LOCAL" == true ]]; then
        cp "${SRC}/${pkg}/"*.py "${TARIS_HOME}/${pkg}/" 2>/dev/null || true
      else
        sshpass -p "$REMOTE_PASS" scp -o StrictHostKeyChecking=no \
          "${SRC}/${pkg}/"*.py "${REMOTE_USER}@${REMOTE_HOST}:${TARIS_HOME}/${pkg}/" 2>/dev/null || true
      fi
      info "  ${pkg}/*.py"
    fi
  done

  # Entry points
  for f in bot_web.py telegram_menu_bot.py voice_assistant.py gmail_digest.py; do
    if [[ -f "${SRC}/${f}" ]]; then
      if [[ "$IS_LOCAL" == true ]]; then
        cp "${SRC}/${f}" "${TARIS_HOME}/${f}"
      else
        sshpass -p "$REMOTE_PASS" scp -o StrictHostKeyChecking=no \
          "${SRC}/${f}" "${REMOTE_USER}@${REMOTE_HOST}:${TARIS_HOME}/${f}"
      fi
      info "  ${f}"
    fi
  done

  # Data / config files
  if [[ "$IS_LOCAL" == true ]]; then
    cp "${SRC}/strings.json" "${SRC}/release_notes.json" "${TARIS_HOME}/"
  else
    sshpass -p "$REMOTE_PASS" scp -o StrictHostKeyChecking=no \
      "${SRC}/strings.json" "${SRC}/release_notes.json" \
      "${REMOTE_USER}@${REMOTE_HOST}:${TARIS_HOME}/"
  fi
  info "  strings.json release_notes.json"

  # Screens DSL
  if [[ -d "${SRC}/screens" ]]; then
    _exec "mkdir -p ${TARIS_HOME}/screens"
    if [[ "$IS_LOCAL" == true ]]; then
      cp "${SRC}/screens/"*.yaml "${TARIS_HOME}/screens/" 2>/dev/null || true
      [[ -f "${SRC}/screens/screen.schema.json" ]] && \
        cp "${SRC}/screens/screen.schema.json" "${TARIS_HOME}/screens/" || true
    else
      sshpass -p "$REMOTE_PASS" scp -o StrictHostKeyChecking=no \
        "${SRC}/screens/"*.yaml \
        "${REMOTE_USER}@${REMOTE_HOST}:${TARIS_HOME}/screens/" 2>/dev/null || true
      [[ -f "${SRC}/screens/screen.schema.json" ]] && \
        sshpass -p "$REMOTE_PASS" scp -o StrictHostKeyChecking=no \
          "${SRC}/screens/screen.schema.json" \
          "${REMOTE_USER}@${REMOTE_HOST}:${TARIS_HOME}/screens/" || true
    fi
    info "  screens/"
  fi

  # Web templates + static
  if [[ "$IS_LOCAL" == true ]]; then
    cp -r "${SRC}/web/templates/." "${TARIS_HOME}/web/templates/"
    cp -r "${SRC}/web/static/." "${TARIS_HOME}/web/static/"
  else
    sshpass -p "$REMOTE_PASS" scp -o StrictHostKeyChecking=no -r \
      "${SRC}/web/templates/" "${SRC}/web/static/" \
      "${REMOTE_USER}@${REMOTE_HOST}:${TARIS_HOME}/web/"
  fi
  info "  web/templates/ web/static/"

  # Tests
  if [[ -d "${SRC}/tests" ]]; then
    if [[ "$IS_LOCAL" == true ]]; then
      mkdir -p "${TARIS_HOME}/tests"
      cp -r "${SRC}/tests/." "${TARIS_HOME}/tests/"
    else
      sshpass -p "$REMOTE_PASS" scp -o StrictHostKeyChecking=no -r \
        "${SRC}/tests/" "${REMOTE_USER}@${REMOTE_HOST}:${TARIS_HOME}/"
    fi
    info "  tests/"
  fi

  # Setup scripts (for migrate, install)
  if [[ -d "${SRC}/setup" ]]; then
    if [[ "$IS_LOCAL" == true ]]; then
      cp "${SRC}/setup/"*.py "${TARIS_HOME}/setup/" 2>/dev/null || true
      cp "${SRC}/setup/"*.sh "${TARIS_HOME}/setup/" 2>/dev/null || true
    else
      sshpass -p "$REMOTE_PASS" scp -o StrictHostKeyChecking=no \
        "${SRC}/setup/"*.py "${REMOTE_USER}@${REMOTE_HOST}:${TARIS_HOME}/setup/" 2>/dev/null || true
      sshpass -p "$REMOTE_PASS" scp -o StrictHostKeyChecking=no \
        "${SRC}/setup/"*.sh "${REMOTE_USER}@${REMOTE_HOST}:${TARIS_HOME}/setup/" 2>/dev/null || true
    fi
    info "  setup/*.py *.sh"
  fi

  ok "All files deployed to ${TARIS_HOME}"
}

# =============================================================================
# ACTION: PATCH (specific files)
# =============================================================================
action_patch() {
  hdr "Patch — deploying ${PATCH_FILES}"

  # Parse comma-separated file list
  IFS=',' read -ra FILES <<< "$PATCH_FILES"
  for rel_path in "${FILES[@]}"; do
    rel_path="${rel_path// /}"   # trim spaces
    src_path="${SRC}/${rel_path}"
    [[ -f "$src_path" ]] || { warn "File not found: ${src_path}"; continue; }
    # Determine dest path: strip leading "src/" from rel_path
    dest_path="${TARIS_HOME}/${rel_path}"
    dest_dir="$(dirname "$dest_path")"
    _mkdir_p "$dest_dir"
    _cp "$src_path" "$dest_path"
    info "  Patched: ${rel_path}"
  done
  ok "Patch complete"
}

# =============================================================================
# SERVICE FILE DEPLOYMENT
# =============================================================================
_deploy_service_files() {
  hdr "Service files"
  if [[ "$IS_DOCKER" == true ]]; then
    ok "VPS Docker — service files managed by Docker Compose; skipping"
    return
  fi
  SVC_UPDATED=false

  if [[ "$VARIANT" == "openclaw" ]]; then
    # User systemd services
    if [[ "$IS_LOCAL" == true ]]; then
      mkdir -p "${HOME}/.config/systemd/user"
      for svc in taris-telegram taris-web taris-voice; do
        SVC_SRC="${SRC}/services/${svc}.service"
        SVC_DST="${HOME}/.config/systemd/user/${svc}.service"
        [[ -f "$SVC_SRC" ]] || continue
        if ! cmp -s "$SVC_SRC" "$SVC_DST" 2>/dev/null; then
          cp "$SVC_SRC" "$SVC_DST"
          SVC_UPDATED=true
          info "  Updated: ${svc}.service"
        fi
      done
    else
      _exec "mkdir -p ${SVC_DIR_REMOTE:-~/.config/systemd/user}"
      for svc in taris-telegram taris-web; do
        SVC_SRC="${SRC}/services/${svc}.service"
        [[ -f "$SVC_SRC" ]] || continue
        sshpass -p "$REMOTE_PASS" scp -o StrictHostKeyChecking=no \
          "$SVC_SRC" "${REMOTE_USER}@${REMOTE_HOST}:/tmp/${svc}.service"
        CHANGED=$(_exec "
          if ! cmp -s /tmp/${svc}.service ~/.config/systemd/user/${svc}.service 2>/dev/null; then
            mkdir -p ~/.config/systemd/user
            cp /tmp/${svc}.service ~/.config/systemd/user/${svc}.service
            echo UPDATED
          fi
          rm -f /tmp/${svc}.service
        " 2>/dev/null || true)
        [[ "$CHANGED" == *UPDATED* ]] && SVC_UPDATED=true && info "  Updated: ${svc}.service" || true
      done
    fi
  else
    # System systemd services (picoclaw)
    for svc in taris-telegram taris-web taris-voice; do
      SVC_SRC="${SRC}/services/${svc}.service"
      [[ -f "$SVC_SRC" ]] || continue
      sshpass -p "$REMOTE_PASS" scp -o StrictHostKeyChecking=no \
        "$SVC_SRC" "${REMOTE_USER}@${REMOTE_HOST}:/tmp/${svc}.service"
      CHANGED=$(sshpass -p "$REMOTE_PASS" ssh -o StrictHostKeyChecking=no \
        "${REMOTE_USER}@${REMOTE_HOST}" \
        "if ! cmp -s /tmp/${svc}.service /etc/systemd/system/${svc}.service 2>/dev/null; then
           echo '$REMOTE_PASS' | sudo -S cp /tmp/${svc}.service /etc/systemd/system/${svc}.service
           echo UPDATED
         fi
         rm -f /tmp/${svc}.service" 2>/dev/null || true)
      [[ "$CHANGED" == *UPDATED* ]] && SVC_UPDATED=true && info "  Updated: ${svc}.service" || true
    done
  fi

  if [[ "$SVC_UPDATED" == true ]]; then
    _daemon_reload
    ok "Service files updated, daemon reloaded"
  else
    ok "Service files unchanged"
  fi
}

# =============================================================================
# ACTION: RESTART
# =============================================================================
action_restart() {
  hdr "Restart services"
  if [[ "$IS_DOCKER" == true ]]; then
    _exec "sudo docker restart ${DOCKER_CONTAINERS[*]} 2>/dev/null || docker restart ${DOCKER_CONTAINERS[*]}"
    ok "Docker containers restarted: ${DOCKER_CONTAINERS[*]}"
  elif [[ "$IS_LOCAL" == true ]]; then
    ACTIVE=()
    for svc in "${SERVICES[@]}"; do
      systemctl --user is-active --quiet "$svc" 2>/dev/null && ACTIVE+=("$svc") || true
    done
    if [[ ${#ACTIVE[@]} -eq 0 ]]; then
      warn "No active services found — starting ${SERVICES[*]}"
      systemctl --user start "${SERVICES[@]}" 2>/dev/null || true
    else
      systemctl --user restart "${ACTIVE[@]}"
    fi
    ok "Restarted: ${SERVICES[*]}"
  else
    if [[ "$VARIANT" == "picoclaw" ]]; then
      sshpass -p "$REMOTE_PASS" ssh -o StrictHostKeyChecking=no \
        "${REMOTE_USER}@${REMOTE_HOST}" \
        "echo '$REMOTE_PASS' | sudo -S systemctl restart ${SERVICES[*]} 2>/dev/null || true"
    else
      _exec "systemctl --user restart ${SERVICES[*]} 2>/dev/null || true"
    fi
    ok "Services restarted on ${REMOTE_HOST}"
  fi
  sleep 6
}

# =============================================================================
# SYNC VERIFICATION (local deploy only)
# =============================================================================
_verify_sync() {
  if [[ "$IS_LOCAL" == true ]]; then
    SYNC_FAIL=()
    for f in core/bot_config.py core/bot_llm.py telegram_menu_bot.py bot_web.py; do
      diff "${SRC}/${f}" "${TARIS_HOME}/${f}" >/dev/null 2>&1 || SYNC_FAIL+=("$f")
    done
    if [[ ${#SYNC_FAIL[@]} -gt 0 ]]; then
      fail "Sync mismatch: ${SYNC_FAIL[*]} — deploy may not have completed"
    fi
    ok "Sync verified"
  fi
}

# =============================================================================
# SMOKE TESTS
# =============================================================================
_run_smoke_tests() {
  hdr "Smoke tests"
  if [[ "$NO_TESTS" == true ]]; then
    warn "Skipping smoke tests (--no-tests)"
    return
  fi

  FAIL_COUNT=0
  if [[ "$IS_DOCKER" == true ]]; then
    # Run smoke tests inside the running telegram container
    for T in $SMOKE_TESTS; do
      RESULT=$(_exec "docker exec ${DOCKER_CONTAINERS[0]} \
        bash -c 'DEVICE_VARIANT=openclaw PYTHONPATH=/app \
        python3 /app/tests/test_voice_regression.py --test $T 2>&1 \
        | grep -E \"PASS|FAIL|SKIP|WARN\" | tail -2'" 2>/dev/null || echo "SKIP (docker exec error)")
      echo "  $T: ${RESULT:-skipped}"
      echo "$RESULT" | grep -qE "^\S.*\s+FAIL\s" && FAIL_COUNT=$((FAIL_COUNT+1)) || true
    done
  elif [[ "$IS_LOCAL" == true ]]; then
    for T in $SMOKE_TESTS; do
      RESULT=$(DEVICE_VARIANT="${DEVICE_VARIANT}" PYTHONPATH="${TARIS_HOME}" \
        python3 "${TARIS_HOME}/tests/test_voice_regression.py" \
        --test "$T" 2>&1 | grep -E 'PASS|FAIL|SKIP|WARN' | tail -2) || true
      echo "  $T: ${RESULT:-skipped}"
      echo "$RESULT" | grep -qE "^\S.*\s+FAIL\s" && FAIL_COUNT=$((FAIL_COUNT+1)) || true
    done
  else
    for T in $SMOKE_TESTS; do
      RESULT=$(_exec "DEVICE_VARIANT=${DEVICE_VARIANT} PYTHONPATH=${TARIS_HOME} \
        python3 ${TARIS_HOME}/tests/test_voice_regression.py \
        --test $T 2>&1 | grep -E 'PASS|FAIL|SKIP|WARN' | tail -2" 2>/dev/null || echo "SKIP (runner error)")
      echo "  $T: ${RESULT:-skipped}"
      echo "$RESULT" | grep -qE "^\S.*\s+FAIL\s" && FAIL_COUNT=$((FAIL_COUNT+1)) || true
    done
  fi

  if [[ $FAIL_COUNT -gt 0 ]]; then
    warn "$FAIL_COUNT smoke test(s) FAILED — review output above"
  else
    ok "Smoke tests passed ✓"
  fi
}

# =============================================================================
# ACTION: INSTALL (full install with third-party)
# =============================================================================
action_install() {
  hdr "Install — full setup for ${VARIANT}"

  if [[ "$VARIANT" == "openclaw" ]]; then
    INSTALL_CMD="
set -e
TARIS_HOME='${TARIS_HOME}'

# Python dependencies
pip3 install --break-system-packages --quiet \
  pyTelegramBotAPI requests faster-whisper fastembed \
  flask flask-login flask-sqlalchemy \
  python-docx PyPDF2 markdown beautifulsoup4 \
  2>/dev/null || pip3 install --user --quiet \
  pyTelegramBotAPI requests faster-whisper fastembed \
  flask flask-login flask-sqlalchemy \
  python-docx PyPDF2 markdown beautifulsoup4 2>/dev/null || true

# sqlite-vec extension
ARCH=\$(uname -m)
VEC_URL=\"https://github.com/asg017/sqlite-vec/releases/latest/download/sqlite_vec-linux-\${ARCH}.tar.gz\"
wget -q \"\$VEC_URL\" -O /tmp/sqlite_vec.tar.gz && \
  tar -xzf /tmp/sqlite_vec.tar.gz -C /usr/local/lib 2>/dev/null || \
  tar -xzf /tmp/sqlite_vec.tar.gz -C ~/.local/lib 2>/dev/null || true
rm -f /tmp/sqlite_vec.tar.gz

echo INSTALL_OK"
    _exec "$INSTALL_CMD" | grep -q INSTALL_OK || warn "Install had warnings"

    # Deploy service files
    _deploy_service_files

    # Enable and start services
    if [[ "$IS_LOCAL" == true ]]; then
      systemctl --user enable taris-telegram taris-web 2>/dev/null || true
      systemctl --user start taris-telegram taris-web 2>/dev/null || true
    else
      _exec "systemctl --user enable taris-telegram taris-web 2>/dev/null || true
             systemctl --user start taris-telegram taris-web 2>/dev/null || true"
    fi
    ok "OpenClaw installation complete"

  elif [[ "$VARIANT" == "picoclaw" ]]; then
    INSTALL_CMD="echo '\$PI_PWD' | sudo -S bash -c '
set -e

# System packages
apt-get install -y --quiet ffmpeg libopus-dev python3-pip sshpass 2>/dev/null || true

# Python dependencies
pip3 install --break-system-packages --quiet \
  pyTelegramBotAPI requests flask flask-login flask-sqlalchemy \
  python-docx PyPDF2 markdown 2>/dev/null || true

echo INSTALL_OK'"
    _exec_sudo "apt-get install -y --quiet ffmpeg libopus-dev python3-pip 2>/dev/null || true && echo INSTALL_OK" | \
      grep -q INSTALL_OK || warn "System package install had warnings"
    _exec "pip3 install --break-system-packages --quiet pyTelegramBotAPI requests flask flask-login flask-sqlalchemy 2>/dev/null || true"

    # Deploy service files (system)
    _deploy_service_files

    # Enable and start
    _exec_sudo "systemctl enable taris-telegram taris-web && systemctl start taris-telegram taris-web" || true
    ok "PicoClaw installation complete"
  fi
}

# =============================================================================
# DATA DIRECTORY CHECK
# =============================================================================
_check_data_dirs() {
  hdr "Data directory check"
  if [[ "$IS_DOCKER" == true ]]; then
    CHECK_CMD="
missing=()
for f in bot.env; do
  [[ -f ${DOCKER_DATA_HOME}/\$f ]] || missing+=(\"\$f\")
done
[[ \${#missing[@]} -gt 0 ]] && echo \"MISSING: \${missing[*]}\" || echo OK"
  else
    CHECK_CMD="
missing=()
for d in calendar notes docs screens web/templates web/static; do
  [[ -d ${TARIS_HOME}/\$d ]] || missing+=(\"\$d\")
done
for f in taris.db bot.env; do
  [[ -f ${TARIS_HOME}/\$f ]] || missing+=(\"\$f\")
done
[[ \${#missing[@]} -gt 0 ]] && echo \"MISSING: \${missing[*]}\" || echo OK"
  fi

  RESULT=$(_exec "$CHECK_CMD" 2>/dev/null || echo "MISSING: (check failed)")
  if [[ "$RESULT" == OK ]]; then
    ok "All data dirs present"
  else
    warn "${RESULT}"
    warn "This may be a first-time install — consider running: --action install"
    if [[ "$YES" == false ]]; then
      ask "Continue anyway?" || { echo "Aborted."; exit 2; }
    fi
  fi
}

# =============================================================================
# GIT CHECKOUT
# =============================================================================
_git_checkout() {
  [[ -z "$GIT_REF" ]] && return
  hdr "Git checkout: ${GIT_REF}"
  cd "$PROJECT"
  git fetch --quiet 2>/dev/null || true
  git checkout "$GIT_REF" --quiet && ok "Checked out: ${GIT_REF}" || \
    fail "git checkout '${GIT_REF}' failed"
}

# =============================================================================
# SUMMARY
# =============================================================================
_print_summary() {
  NEW_VER="$(_get_version 2>/dev/null || echo '?')"
  echo ""
  echo "╔══════════════════════════════════════════════════════════╗"
  echo "║                    Summary                              ║"
  echo "╚══════════════════════════════════════════════════════════╝"
  printf "  %-12s %s\n" "Action:"  "$ACTION"
  printf "  %-12s %s\n" "Target:"  "$TARGET (${IS_LOCAL:+local}${REMOTE_HOST})"
  printf "  %-12s %s\n" "Version:" "${DEPLOYED_VER} → ${NEW_VER}"
  if [[ -n "${BNAME:-}" ]]; then
    printf "  %-12s %s\n" "Backup:"  "backup/snapshots/${BNAME}/"
  fi
  echo ""
  if [[ "$TARGET" == "vps" ]]; then
    echo "  Next steps (VPS / feature branch):"
    echo "    1. Test the bot via Telegram (feature branch)"
    echo "    2. When feature is ready: merge to master, then deploy to TariStation1"
    echo "       bash src/setup/taris_deploy.sh --action deploy --target ts1"
  elif [[ "$TARGET" == "ts2" || "$TARGET" == "pi2" ]]; then
    echo "  Next steps:"
    echo "    1. Test the bot in Telegram"
    echo "    2. Run full regression:"
    if [[ "$VARIANT" == "openclaw" ]]; then
      echo "       DEVICE_VARIANT=openclaw PYTHONPATH=~/.taris \\"
      echo "         python3 src/tests/test_voice_regression.py"
    else
      echo "       python3 ~/.taris/tests/test_voice_regression.py"
    fi
    echo "    3. After tests pass, deploy to production:"
    if [[ "$TARGET" == "ts2" ]]; then
      echo "       bash src/setup/taris_deploy.sh --action deploy --target ts1"
    else
      echo "       bash src/setup/taris_deploy.sh --action deploy --target pi1"
    fi
  else
    echo -e "  ${G}Production target deployed and verified ✅${N}"
  fi
  echo ""
}

# =============================================================================
# MAIN FLOW
# =============================================================================
_check_connectivity
_detect_versions
_print_header
_confirm

# Git checkout if requested
_git_checkout

# Pre-action backup (for deploy/patch/migrate/install unless --no-backup)
if [[ "$NO_BACKUP" == false ]] && [[ "$ACTION" =~ ^(deploy|patch|migrate|install)$ ]]; then
  ORIG_BACKUP_TYPE="$BACKUP_TYPE"
  BACKUP_TYPE="data"
  action_backup
  BACKUP_TYPE="$ORIG_BACKUP_TYPE"
fi

# Dispatch action
case "$ACTION" in
  verify)
    action_verify
    ;;
  backup)
    action_backup
    ;;
  restart)
    action_restart
    action_verify
    ;;
  migrate)
    _svc_ctl stop "${SERVICES[@]}" 2>/dev/null || true
    sleep 2
    action_migrate
    action_restart
    action_verify
    ;;
  patch)
    _check_data_dirs
    action_patch
    _deploy_service_files
    action_restart
    action_verify
    _run_smoke_tests
    ;;
  install)
    action_install
    _deploy_files
    if [[ "$NO_MIGRATE" == false ]]; then action_migrate; fi
    action_restart
    action_verify
    _run_smoke_tests
    ;;
  deploy)
    _check_data_dirs
    _deploy_files
    _deploy_service_files
    _verify_sync
    if [[ "$NO_MIGRATE" == false ]]; then
      # Only auto-migrate if migrate_to_db.py exists on target
      _exec "test -f ${TARIS_HOME}/setup/migrate_to_db.py" 2>/dev/null && \
        action_migrate || true
    fi
    action_restart
    action_verify
    _run_smoke_tests
    ;;
esac

_print_summary
