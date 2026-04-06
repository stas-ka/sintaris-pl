#!/bin/bash
# =============================================================================
# update_from_git.sh — Update Taris Bot from a Git Repository
# =============================================================================
# Clones or pulls the bot's Git repository, then deploys updated files.
# Does NOT touch secrets (bot.env, config.json, gmail_credentials.json).
#
# First run:  sudo bash update_from_git.sh --repo https://github.com/USER/REPO
# Later runs: sudo bash update_from_git.sh   (repo URL remembered)
#
# Options:
#   --repo <url>     Git repo URL (saved to /etc/taris-repo.conf on first run)
#   --branch <name>  Branch to track (default: main)
#   --check          Show latest commit vs installed, do not update
#   --force          Redeploy even if already at latest commit
# =============================================================================

set -euo pipefail

# ── defaults ──────────────────────────────────────────────────────────────────
TARIS_USER="${TARIS_USER:-stas}"
TARIS_DIR="/home/${TARIS_USER}/.taris"
SYSTEMD_DIR="/etc/systemd/system"
BACKUP_DIR="/tmp/taris-backup"
REPO_CACHE_FILE="/etc/taris-repo.conf"
REPO_DIR="/opt/taris-repo"

GIT_REPO=""
GIT_BRANCH="main"
FORCE=false
CHECK_ONLY=false

# ── colours ───────────────────────────────────────────────────────────────────
G="\e[32m"; Y="\e[33m"; R="\e[31m"; B="\e[34m"; N="\e[0m"
ok()   { echo -e "${G}[OK]${N}  $*"; }
info() { echo -e "${B}[..]${N}  $*"; }
warn() { echo -e "${Y}[!]${N}   $*"; }
fail() { echo -e "${R}[FAIL]${N} $*"; exit 1; }

# ── args ──────────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)   GIT_REPO="$2";   shift 2 ;;
    --branch) GIT_BRANCH="$2"; shift 2 ;;
    --force)  FORCE=true;      shift ;;
    --check)  CHECK_ONLY=true; shift ;;
    *) warn "Unknown argument: $1"; shift ;;
  esac
done

[[ "${CHECK_ONLY}" == "false" && "$(id -u)" -ne 0 ]] && \
  fail "Run as root: sudo bash $0"

# ── load or save repo URL ─────────────────────────────────────────────────────
if [[ -z "${GIT_REPO}" && -f "${REPO_CACHE_FILE}" ]]; then
  source "${REPO_CACHE_FILE}"
fi
[[ -z "${GIT_REPO}" ]] && \
  fail "No repo URL. Pass --repo https://github.com/USER/REPO on first run."

# Save for future runs
if [[ "${CHECK_ONLY}" == "false" ]]; then
  echo "GIT_REPO=\"${GIT_REPO}\"" > "${REPO_CACHE_FILE}"
  echo "GIT_BRANCH=\"${GIT_BRANCH}\"" >> "${REPO_CACHE_FILE}"
fi

echo ""
echo "=============================================="
echo "  Taris Bot — Update from Git"
echo "=============================================="
echo "  Repo   : ${GIT_REPO}"
echo "  Branch : ${GIT_BRANCH}"
echo "  Cache  : ${REPO_DIR}"
echo ""

# ── ensure git is available ──────────────────────────────────────────────────
command -v git >/dev/null 2>&1 || \
  { info "Installing git..."; apt-get install -y -q git; }

# ── Step 1: clone or update the repo ─────────────────────────────────────────
if [[ -d "${REPO_DIR}/.git" ]]; then
  info "Pulling latest from ${GIT_BRANCH}..."
  git -C "${REPO_DIR}" fetch --quiet origin
  GIT_REMOTE_HASH=$(git -C "${REPO_DIR}" rev-parse "origin/${GIT_BRANCH}")
  GIT_LOCAL_HASH=$(git -C "${REPO_DIR}" rev-parse HEAD)
  GIT_REMOTE_MSG=$(git -C "${REPO_DIR}" log -1 --format="%s (%cr)" \
    "origin/${GIT_BRANCH}" 2>/dev/null)
else
  info "Cloning ${GIT_REPO}..."
  git clone --quiet --branch "${GIT_BRANCH}" --depth 50 \
    "${GIT_REPO}" "${REPO_DIR}"
  GIT_REMOTE_HASH=$(git -C "${REPO_DIR}" rev-parse HEAD)
  GIT_LOCAL_HASH="none"
  GIT_REMOTE_MSG=$(git -C "${REPO_DIR}" log -1 --format="%s (%cr)")
fi

INSTALLED_HASH="none"
if [[ -f "${TARIS_DIR}/installed_git_hash.txt" ]]; then
  INSTALLED_HASH=$(cat "${TARIS_DIR}/installed_git_hash.txt" | tr -d '[:space:]')
fi

echo "  Installed : ${INSTALLED_HASH:0:12}"
echo "  Available : ${GIT_REMOTE_HASH:0:12}  — ${GIT_REMOTE_MSG}"
echo ""

if [[ "${CHECK_ONLY}" == "true" ]]; then
  if [[ "${GIT_REMOTE_HASH}" == "${INSTALLED_HASH}" ]]; then
    ok "Up to date"
  else
    warn "Update available: ${INSTALLED_HASH:0:12} → ${GIT_REMOTE_HASH:0:12}"
  fi
  exit 0
fi

if [[ "${GIT_REMOTE_HASH}" == "${INSTALLED_HASH}" && "${FORCE}" == "false" ]]; then
  ok "Already at latest commit (${GIT_REMOTE_HASH:0:12}). Use --force to redeploy."
  exit 0
fi

# ── Step 2: merge remote changes ─────────────────────────────────────────────
git -C "${REPO_DIR}" checkout --quiet "${GIT_BRANCH}" 2>/dev/null || true
git -C "${REPO_DIR}" reset --hard --quiet "origin/${GIT_BRANCH}"
ok "Repo at $(git -C "${REPO_DIR}" rev-parse --short HEAD)"

# ── Step 3: locate src/ in the repo ──────────────────────────────────────────
SRC_DIR="${REPO_DIR}"
[[ -d "${REPO_DIR}/src" ]] && SRC_DIR="${REPO_DIR}/src"

# ── Step 4: back up current files ────────────────────────────────────────────
info "Backing up current installation to ${BACKUP_DIR}..."
rm -rf "${BACKUP_DIR}" && mkdir -p "${BACKUP_DIR}"
BOT_FILES=(
  telegram_menu_bot.py bot_web.py voice_assistant.py gmail_digest.py
  strings.json release_notes.json installed_git_hash.txt
)
for f in "${BOT_FILES[@]}"; do
  [[ -f "${TARIS_DIR}/${f}" ]] && cp "${TARIS_DIR}/${f}" "${BACKUP_DIR}/"
done
# Backup package subdirectories
for pkg in core telegram features ui security screens web; do
  if [[ -d "${TARIS_DIR}/${pkg}" ]]; then
    cp -r "${TARIS_DIR}/${pkg}" "${BACKUP_DIR}/${pkg}"
  fi
done
for svc in taris-telegram taris-voice; do
  [[ -f "${SYSTEMD_DIR}/${svc}.service" ]] && \
    cp "${SYSTEMD_DIR}/${svc}.service" "${BACKUP_DIR}/"
done
ok "Backed up to ${BACKUP_DIR}"

# ── Step 5: deploy bot source files ──────────────────────────────────────────
info "Deploying bot files to ${TARIS_DIR}..."
DEPLOYED=0
for f in telegram_menu_bot.py bot_web.py voice_assistant.py gmail_digest.py \
          strings.json release_notes.json; do
  if [[ -f "${SRC_DIR}/${f}" ]]; then
    if ! cmp -s "${SRC_DIR}/${f}" "${TARIS_DIR}/${f}" 2>/dev/null; then
      cp "${SRC_DIR}/${f}" "${TARIS_DIR}/${f}"
      info "  → ${f} (changed)"
      ((DEPLOYED++))
    fi
  else
    warn "  Not in repo: ${f}"
  fi
done

# Deploy package subdirectories (core/, telegram/, features/, ui/, security/, screens/, web/)
for pkg in core telegram features ui security screens; do
  if [[ -d "${SRC_DIR}/${pkg}" ]]; then
    mkdir -p "${TARIS_DIR}/${pkg}"
    while IFS= read -r -d '' src_file; do
      rel="${src_file#${SRC_DIR}/${pkg}/}"
      dst_file="${TARIS_DIR}/${pkg}/${rel}"
      mkdir -p "$(dirname "${dst_file}")"
      if ! cmp -s "${src_file}" "${dst_file}" 2>/dev/null; then
        cp "${src_file}" "${dst_file}"
        info "  → ${pkg}/${rel} (changed)"
        ((DEPLOYED++))
      fi
    done < <(find "${SRC_DIR}/${pkg}" -name "*.py" -o -name "*.yaml" -o -name "*.json" \
              | grep -v '__pycache__' | tr '\n' '\0' | sort -z)
  fi
done
# Deploy web/ (templates + static)
if [[ -d "${SRC_DIR}/web" ]]; then
  mkdir -p "${TARIS_DIR}/web"
  while IFS= read -r -d '' src_file; do
    rel="${src_file#${SRC_DIR}/web/}"
    dst_file="${TARIS_DIR}/web/${rel}"
    mkdir -p "$(dirname "${dst_file}")"
    if ! cmp -s "${src_file}" "${dst_file}" 2>/dev/null; then
      cp "${src_file}" "${dst_file}"
      info "  → web/${rel} (changed)"
      ((DEPLOYED++))
    fi
  done < <(find "${SRC_DIR}/web" -type f | grep -v '__pycache__' | tr '\n' '\0' | sort -z)
fi
ok "${DEPLOYED} files updated"

# ── Step 6: sync service files ────────────────────────────────────────────────
RELOAD_NEEDED=false
SERVICES_DIR="${SRC_DIR}/services"
[[ -d "${REPO_DIR}/src/services" ]] && SERVICES_DIR="${REPO_DIR}/src/services"

if [[ -d "${SERVICES_DIR}" ]]; then
  for svc in taris-telegram taris-voice; do
    SVC_SRC="${SERVICES_DIR}/${svc}.service"
    SVC_DST="${SYSTEMD_DIR}/${svc}.service"
    if [[ -f "${SVC_SRC}" ]] && ! cmp -s "${SVC_SRC}" "${SVC_DST}" 2>/dev/null; then
      cp "${SVC_SRC}" "${SVC_DST}"
      RELOAD_NEEDED=true
      info "  → ${svc}.service (updated)"
    fi
  done
fi

# record installed commit
echo "${GIT_REMOTE_HASH}" > "${TARIS_DIR}/installed_git_hash.txt"
chown -R "${TARIS_USER}:${TARIS_USER}" "${TARIS_DIR}"

# ── Step 7: restart services ──────────────────────────────────────────────────
if [[ "${DEPLOYED}" -gt 0 || "${RELOAD_NEEDED}" == "true" ]]; then
  info "Restarting services..."
  [[ "${RELOAD_NEEDED}" == "true" ]] && systemctl daemon-reload

  FAILED=false
  for svc in taris-telegram taris-voice; do
    if systemctl is-active --quiet "${svc}" 2>/dev/null || \
       systemctl is-enabled --quiet "${svc}" 2>/dev/null; then
      if ! systemctl restart "${svc}" 2>/dev/null; then
        warn "Failed to restart ${svc} — rolling back"
        FAILED=true; break
      fi
      ok "Restarted ${svc}"
    fi
  done

  if [[ "${FAILED}" == "true" ]]; then
    warn "Applying rollback from ${BACKUP_DIR}..."
    find "${BACKUP_DIR}" -maxdepth 1 \( -name "*.py" -o -name "*.json" \) \
      -exec cp {} "${TARIS_DIR}/" \; 2>/dev/null || true
    [[ -f "${BACKUP_DIR}/installed_git_hash.txt" ]] && \
      cp "${BACKUP_DIR}/installed_git_hash.txt" "${TARIS_DIR}/"
    for pkg in core telegram features ui security screens web; do
      [[ -d "${BACKUP_DIR}/${pkg}" ]] && cp -r "${BACKUP_DIR}/${pkg}" "${TARIS_DIR}/"
    done
    for svc in taris-telegram taris-voice; do
      [[ -f "${BACKUP_DIR}/${svc}.service" ]] && \
        cp "${BACKUP_DIR}/${svc}.service" "${SYSTEMD_DIR}/"
    done
    systemctl daemon-reload
    for svc in taris-telegram taris-voice; do
      systemctl restart "${svc}" 2>/dev/null || true
    done
    fail "Update failed — rolled back to ${INSTALLED_HASH:0:12}"
  fi
else
  ok "No files changed — services not restarted"
fi

# ── verify ────────────────────────────────────────────────────────────────────
echo ""
sleep 3
journalctl -u taris-telegram -n 5 --no-pager 2>/dev/null | \
  grep -E 'Version|Polling|ERROR' || true

echo ""
echo "=============================================="
ok "Update complete: ${INSTALLED_HASH:0:12} → ${GIT_REMOTE_HASH:0:12}"
echo "  Commit: ${GIT_REMOTE_MSG}"
echo "=============================================="
