#!/usr/bin/env bash
# =============================================================================
# install_openclaw.sh — Full Fresh Install of Taris on OpenClaw / TariStation
# =============================================================================
# Bootstraps an Ubuntu/Debian x86_64 machine into a fully working Taris
# OpenClaw installation: Python packages, voice pipeline (Piper TTS +
# faster-whisper STT), Ollama LLM, PostgreSQL Docker container (optional),
# systemd user services, and bot configuration.
#
# Run ONCE on a fresh TariStation machine as a normal user (NOT root):
#   bash src/setup/install_openclaw.sh [options]
#
# Options:
#   --variant  ts2|ts1   Target identity label (default: ts2 = TariStation2)
#   --voice              Install Piper TTS + faster-whisper STT (default: yes)
#   --no-voice           Skip voice pipeline install
#   --llm                Install Ollama LLM (default: yes)
#   --no-llm             Skip Ollama install
#   --gpu                Configure AMD GPU acceleration for Ollama
#   --postgres           Set up PostgreSQL via Docker (default: yes if docker available)
#   --no-postgres        Use SQLite storage backend instead
#   --yes                Skip confirmation prompts
#   -h, --help
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
ask_yn(){ printf "${Y}[?]${N}    $* [Y/n] "; read -r _ANS; [[ "${_ANS,,}" != n* ]]; }
prompt(){ printf "${Y}[?]${N}    $*: "; read -r _VAL; echo "$_VAL"; }

# ── Locate project root ───────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SRC="${PROJECT}/src"

# ── Defaults ─────────────────────────────────────────────────────────────────
VARIANT="ts2"
INSTALL_VOICE=true
INSTALL_LLM=true
GPU_MODE=false
SETUP_POSTGRES=""   # auto-detect
YES=false
TARIS_HOME="${HOME}/.taris"
TARIS_USER="${USER}"

# ── Args ──────────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --variant)    VARIANT="$2"; shift 2 ;;
    --voice)      INSTALL_VOICE=true; shift ;;
    --no-voice)   INSTALL_VOICE=false; shift ;;
    --llm)        INSTALL_LLM=true; shift ;;
    --no-llm)     INSTALL_LLM=false; shift ;;
    --gpu)        GPU_MODE=true; shift ;;
    --postgres)   SETUP_POSTGRES=true; shift ;;
    --no-postgres) SETUP_POSTGRES=false; shift ;;
    --yes|-y)     YES=true; shift ;;
    -h|--help)
      sed -n '2,30p' "${BASH_SOURCE[0]}" | grep '^#' | sed 's/^# *//'
      exit 0 ;;
    *) warn "Unknown option: $1"; shift ;;
  esac
done

# Auto-detect Docker for PostgreSQL
if [[ -z "$SETUP_POSTGRES" ]]; then
  command -v docker >/dev/null 2>&1 && SETUP_POSTGRES=true || SETUP_POSTGRES=false
fi

# ── Header ────────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║    Taris Bot — OpenClaw Fresh Install (TariStation)    ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo "  Variant      : ${VARIANT} (openclaw)"
echo "  Install dir  : ${TARIS_HOME}"
echo "  User         : ${TARIS_USER}"
echo "  Voice pipeline: ${INSTALL_VOICE}"
echo "  Ollama LLM   : ${INSTALL_LLM}$([ "$GPU_MODE" == true ] && echo ' (GPU mode)' || echo '')"
echo "  PostgreSQL   : ${SETUP_POSTGRES}"
echo ""

if [[ "$YES" == false ]]; then
  ask_yn "Proceed with installation?" || { echo "Aborted."; exit 0; }
fi

# ── Step 1: System packages ───────────────────────────────────────────────────
hdr "Step 1/10 — System packages"
PKGS=(python3 python3-pip python3-venv git curl wget ffmpeg portaudio19-dev
      espeak-ng build-essential zstd unzip)
command -v sshpass >/dev/null 2>&1 || PKGS+=(sshpass)

MISSING=()
for pkg in "${PKGS[@]}"; do
  dpkg -l "$pkg" &>/dev/null || MISSING+=("$pkg")
done

if [[ ${#MISSING[@]} -gt 0 ]]; then
  info "Installing: ${MISSING[*]}"
  sudo apt-get update -qq
  sudo apt-get install -y "${MISSING[@]}"
fi
ok "System packages installed"

# ── Step 2: Python packages ───────────────────────────────────────────────────
hdr "Step 2/10 — Python packages"
info "Installing Python dependencies from deploy/requirements.txt ..."
REQ="${PROJECT}/deploy/requirements.txt"
if [[ -f "$REQ" ]]; then
  pip3 install --break-system-packages --quiet -r "$REQ"
else
  # Inline minimal set if no requirements.txt
  pip3 install --break-system-packages --quiet \
    pyTelegramBotAPI faster-whisper scipy sounddevice webrtcvad \
    google-api-python-client google-auth-httplib2 google-auth-oauthlib \
    fastapi "uvicorn[standard]" jinja2 bcrypt PyJWT python-multipart requests \
    fastembed pyyaml jsonschema pdfminer.six python-docx sqlite-vec \
    "psycopg[binary]" psycopg-pool pgvector cryptography
fi
ok "Python packages installed"

# ── Step 3: Create taris directory structure ──────────────────────────────────
hdr "Step 3/10 — Taris directory structure"
for d in core telegram features ui security tests/voice/results \
          screens web/templates web/static calendar notes contacts \
          error_protocols mail_creds; do
  mkdir -p "${TARIS_HOME}/${d}"
done
# Package __init__ files
for pkg in core telegram features ui security; do
  touch "${TARIS_HOME}/${pkg}/__init__.py"
done
ok "Directory structure created at ${TARIS_HOME}"

# ── Step 4: Deploy bot source files ──────────────────────────────────────────
hdr "Step 4/10 — Deploy bot source files"
for pkg in core telegram features ui security; do
  [[ -d "${SRC}/${pkg}" ]] && cp "${SRC}/${pkg}/"*.py "${TARIS_HOME}/${pkg}/" && \
    info "  ${pkg}/*.py" || true
done
for f in bot_web.py telegram_menu_bot.py voice_assistant.py gmail_digest.py; do
  [[ -f "${SRC}/${f}" ]] && cp "${SRC}/${f}" "${TARIS_HOME}/${f}" && info "  ${f}" || true
done
cp "${SRC}/strings.json" "${SRC}/release_notes.json" "${TARIS_HOME}/"
[[ -d "${SRC}/screens" ]] && cp -r "${SRC}/screens/." "${TARIS_HOME}/screens/" && \
  info "  screens/"
[[ -d "${SRC}/web/templates" ]] && cp -r "${SRC}/web/templates/." "${TARIS_HOME}/web/templates/"
[[ -d "${SRC}/web/static" ]] && cp -r "${SRC}/web/static/." "${TARIS_HOME}/web/static/"
[[ -d "${SRC}/tests" ]] && cp -r "${SRC}/tests/." "${TARIS_HOME}/tests/"
ok "Source files deployed"

# ── Step 5: Voice pipeline ───────────────────────────────────────────────────
hdr "Step 5/10 — Voice pipeline (Piper TTS + faster-whisper STT)"
if [[ "$INSTALL_VOICE" == false ]]; then
  warn "Skipping voice pipeline (--no-voice)"
else
  SETUP_VOICE="${SCRIPT_DIR}/setup_voice_openclaw.sh"
  if [[ -f "$SETUP_VOICE" ]]; then
    info "Running setup_voice_openclaw.sh ..."
    TARIS_HOME="${TARIS_HOME}" bash "$SETUP_VOICE"
    ok "Voice pipeline installed"
  else
    warn "setup_voice_openclaw.sh not found at ${SETUP_VOICE}"
  fi
fi

# ── Step 6: Ollama LLM ───────────────────────────────────────────────────────
hdr "Step 6/10 — Ollama LLM"
if [[ "$INSTALL_LLM" == false ]]; then
  warn "Skipping Ollama install (--no-llm)"
else
  SETUP_LLM="${SCRIPT_DIR}/setup_llm_openclaw.sh"
  if [[ -f "$SETUP_LLM" ]]; then
    GPU_FLAG=""
    [[ "$GPU_MODE" == true ]] && GPU_FLAG="--gpu"
    info "Running setup_llm_openclaw.sh ${GPU_FLAG} ..."
    bash "$SETUP_LLM" $GPU_FLAG
    ok "Ollama installed"
  else
    warn "setup_llm_openclaw.sh not found at ${SETUP_LLM}"
  fi
fi

# ── Step 7: PostgreSQL via Docker ─────────────────────────────────────────────
hdr "Step 7/10 — PostgreSQL (storage backend)"
PG_DSN=""
STORE_BACKEND="sqlite"
if [[ "$SETUP_POSTGRES" == false ]]; then
  warn "Using SQLite backend (--no-postgres)"
  STORE_BACKEND="sqlite"
elif command -v docker >/dev/null 2>&1; then
  COMPOSE_FILE="${PROJECT}/deploy/docker-compose.yml"
  if [[ -f "$COMPOSE_FILE" ]]; then
    info "Starting PostgreSQL via docker-compose ..."
    (cd "${PROJECT}/deploy" && docker compose up -d)
    sleep 5
  else
    info "No docker-compose.yml found — starting pgvector container directly ..."
    docker run -d --name local-dev-postgres-1 \
      --restart unless-stopped \
      -e POSTGRES_USER=taris \
      -e POSTGRES_PASSWORD=taris_openclaw_2026 \
      -e POSTGRES_DB=taris \
      -p 127.0.0.1:5432:5432 \
      pgvector/pgvector:pg17 2>/dev/null || \
      docker start local-dev-postgres-1 2>/dev/null || true
    sleep 5
  fi
  # Verify connection
  python3 -c "
import psycopg, sys
try:
  c = psycopg.connect('postgresql://taris:taris_openclaw_2026@localhost:5432/taris', connect_timeout=10)
  print('PG_OK')
  c.close()
except Exception as e:
  print(f'PG_FAIL: {e}')
  sys.exit(1)
" && {
    PG_DSN="postgresql://taris:taris_openclaw_2026@localhost:5432/taris"
    STORE_BACKEND="postgres"
    ok "PostgreSQL connected via Docker ✓"
  } || {
    warn "PostgreSQL connection failed — falling back to SQLite"
    STORE_BACKEND="sqlite"
  }
else
  warn "Docker not available — using SQLite backend"
  STORE_BACKEND="sqlite"
fi

# ── Step 8: bot.env configuration ────────────────────────────────────────────
hdr "Step 8/10 — Bot configuration (bot.env)"
BOT_ENV="${TARIS_HOME}/bot.env"

if [[ -f "$BOT_ENV" ]]; then
  if [[ "$YES" == false ]]; then
    warn "bot.env already exists at ${BOT_ENV}"
    ask "Overwrite with new template?" && WRITE_ENV=true || WRITE_ENV=false
  else
    WRITE_ENV=false
  fi
else
  WRITE_ENV=true
fi

if [[ "$WRITE_ENV" == true ]]; then
  # Interactive prompts for required secrets
  if [[ "$YES" == false ]]; then
    echo ""
    echo "  Enter the following secrets (leave blank to fill in later):"
    BOT_TOKEN=$(prompt "  Telegram BOT_TOKEN (from @BotFather)")
    ALLOWED_USERS=$(prompt "  ALLOWED_USERS (your Telegram chat ID)")
    OPENAI_KEY=$(prompt "  OPENAI_API_KEY (sk-... or leave blank)")
    ROOT_PATH=$(prompt "  ROOT_PATH for web UI proxy (e.g. /supertaris2, or blank for /)")
  else
    BOT_TOKEN="<your_telegram_bot_token>"
    ALLOWED_USERS="<your_telegram_chat_id>"
    OPENAI_KEY=""
    ROOT_PATH=""
  fi

  # Detect Piper paths
  PIPER_BIN=$(find "${TARIS_HOME}/piper" -name piper -type f 2>/dev/null | head -1 || echo "~/.taris/piper/piper")
  PIPER_MODEL=$(find "${TARIS_HOME}" -name "*.onnx" ! -name "*.onnx.json" 2>/dev/null | head -1 || echo "~/.taris/ru_RU-irina-medium.onnx")
  OLLAMA_MODEL="qwen2:0.5b"
  [[ "$GPU_MODE" == true ]] && OLLAMA_MODEL="qwen3:14b"

  cat > "$BOT_ENV" << ENVEOF
# bot.env — Taris OpenClaw (${VARIANT}) — generated by install_openclaw.sh
# Edit and fill in all <placeholder> values before starting services.

# ── Core — Telegram ───────────────────────────────────────────────────────────
BOT_TOKEN=${BOT_TOKEN}
ALLOWED_USERS=${ALLOWED_USERS}
# ADMIN_USERS=<admin_telegram_chat_id>

# ── Deployment variant ────────────────────────────────────────────────────────
DEVICE_VARIANT=openclaw

# ── LLM provider ─────────────────────────────────────────────────────────────
LLM_PROVIDER=openai
# LLM_LOCAL_FALLBACK=1

# ── OpenAI ────────────────────────────────────────────────────────────────────
$([ -n "$OPENAI_KEY" ] && echo "OPENAI_API_KEY=${OPENAI_KEY}" || echo "# OPENAI_API_KEY=sk-...")
# OPENAI_MODEL=gpt-4o-mini

# ── Ollama (local LLM) ───────────────────────────────────────────────────────
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=${OLLAMA_MODEL}
# OLLAMA_THINK=false
# OLLAMA_KEEP_ALIVE=1h

# ── Voice — STT ───────────────────────────────────────────────────────────────
STT_PROVIDER=faster_whisper
STT_LANG=ru
FASTER_WHISPER_MODEL=base
FASTER_WHISPER_DEVICE=cpu
FASTER_WHISPER_COMPUTE=int8

# ── Voice — TTS ───────────────────────────────────────────────────────────────
PIPER_BIN=${PIPER_BIN}
PIPER_MODEL=${PIPER_MODEL}

# ── Storage backend ───────────────────────────────────────────────────────────
STORE_BACKEND=${STORE_BACKEND}
$([ "$STORE_BACKEND" == "postgres" ] && echo "STORE_PG_DSN=${PG_DSN}" || echo "# STORE_PG_DSN=postgresql://taris:password@localhost:5432/taris")

# ── Web UI ────────────────────────────────────────────────────────────────────
$([ -n "$ROOT_PATH" ] && echo "ROOT_PATH=${ROOT_PATH}" || echo "# ROOT_PATH=/supertaris2")
# TARIS_API_TOKEN=<strong_random_token>

# ── RAG / Knowledge base ──────────────────────────────────────────────────────
# RAG_ENABLED=1
# EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2
# EMBED_KEEP_RESIDENT=1
# EMBED_DIMENSION=384

# ── Nextcloud backup (optional) ───────────────────────────────────────────────
# NEXTCLOUD_URL=https://cloud.example.com
# NEXTCLOUD_USER=<username>
# NEXTCLOUD_PASS=<app_password>
# NEXTCLOUD_REMOTE=/TarisBackups
ENVEOF

  chmod 600 "$BOT_ENV"
  ok "bot.env written to ${BOT_ENV}"
  if [[ "$BOT_TOKEN" == *"<"* || -z "$BOT_TOKEN" ]]; then
    warn "⚠  Fill in BOT_TOKEN and ALLOWED_USERS before starting services!"
  fi
else
  ok "Existing bot.env preserved"
fi

# ── Step 9: Systemd user services ────────────────────────────────────────────
hdr "Step 9/10 — Systemd user services"
SVC_DIR="${HOME}/.config/systemd/user"
mkdir -p "$SVC_DIR"

for svc in taris-telegram taris-web; do
  SVC_SRC="${SRC}/services/${svc}.service"
  if [[ -f "$SVC_SRC" ]]; then
    cp "$SVC_SRC" "${SVC_DIR}/${svc}.service"
    info "  Installed: ${svc}.service"
  else
    warn "  Missing: ${SVC_SRC}"
  fi
done

systemctl --user daemon-reload
systemctl --user enable taris-telegram taris-web 2>/dev/null || true
ok "Services installed and enabled"

# ── Step 10: First start + smoke test ────────────────────────────────────────
hdr "Step 10/10 — First start & smoke test"

# Check if secrets are filled
BOT_TOKEN_SET=$(grep "BOT_TOKEN=" "$BOT_ENV" | grep -v "^#" | grep -v "<" | head -1 || true)
if [[ -z "$BOT_TOKEN_SET" ]]; then
  warn "BOT_TOKEN not set in bot.env — skipping service start"
  warn "Edit ${BOT_ENV}, then run:"
  warn "  systemctl --user start taris-telegram taris-web"
else
  if [[ "$YES" == false ]]; then
    ask_yn "Start services now?" && START_SVC=true || START_SVC=false
  else
    START_SVC=true
  fi

  if [[ "$START_SVC" == true ]]; then
    systemctl --user start taris-telegram taris-web
    sleep 5
    JLOG=$(journalctl --user -u taris-telegram -n 15 --no-pager 2>/dev/null)
    echo "$JLOG" | tail -8

    if echo "$JLOG" | grep -q "Polling Telegram"; then
      ok "Bot started and polling Telegram ✓"

      # Quick smoke test
      SRC_VER=$(grep 'BOT_VERSION' "${TARIS_HOME}/core/bot_config.py" | head -1 | cut -d'"' -f2 || echo "?")
      SMOKE_RESULT=$(DEVICE_VARIANT=openclaw PYTHONPATH="${TARIS_HOME}" \
        python3 "${TARIS_HOME}/tests/test_voice_regression.py" \
        --test t_openclaw_stt_routing i18n_string_coverage bot_name_injection \
        2>&1 | tail -4 || echo "test runner unavailable")
      echo "$SMOKE_RESULT"
      ok "Installation complete — version ${SRC_VER}"
    else
      warn "Service not yet polling. Check: journalctl --user -u taris-telegram -n 30 --no-pager"
    fi
  fi
fi

# ── Final summary ─────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║              Installation Summary                       ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo "  Install dir  : ${TARIS_HOME}"
echo "  Variant      : openclaw (${VARIANT})"
echo "  Voice        : ${INSTALL_VOICE}"
echo "  LLM (Ollama) : ${INSTALL_LLM}"
echo "  Storage      : ${STORE_BACKEND}"
echo "  Bot config   : ${BOT_ENV}"
echo ""
echo "  Useful commands:"
echo "    journalctl --user -u taris-telegram -f --no-pager"
echo "    journalctl --user -u taris-web -f --no-pager"
echo "    systemctl --user status taris-telegram taris-web"
echo ""
echo "  To update in the future:"
echo "    bash src/setup/update_openclaw.sh --target ts2"
echo ""
if [[ "$BOT_TOKEN_SET" == "" ]]; then
  echo -e "  ${Y}⚠  ACTION REQUIRED: fill in bot.env then start services:${N}"
  echo "    nano ${BOT_ENV}"
  echo "    systemctl --user start taris-telegram taris-web"
  echo ""
fi
