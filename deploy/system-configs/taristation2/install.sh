#!/usr/bin/env bash
# install-taristation2.sh — Initial setup for TariStation2 (OpenClaw engineering/dev)
#
# Target:   Ubuntu/Debian, CPU-only (7.6GB RAM), local machine
# Services: Telegram bot, Web UI, Voice assistant, Ollama (small models), SSH tunnel
# Run as:   stas (user with sudo)
# Usage:    bash install-taristation2.sh

set -euo pipefail
TARIS_DIR="$HOME/.taris"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== 1. System packages ==="
sudo apt update
sudo apt install -y \
    python3 python3-pip python3-venv \
    ffmpeg \
    autossh \
    postgresql postgresql-contrib \
    git curl wget \
    libsndfile1 portaudio19-dev \
    pipewire pipewire-pulse

echo "=== 2. Ollama (CPU-only) ==="
curl -fsSL https://ollama.com/install.sh | sh
# Pull small model for CPU (fits in 7.6GB RAM)
ollama pull qwen3.5:0.8b
# IMPORTANT: FASTER_WHISPER_PRELOAD=0 in bot.env prevents OOM when Ollama is running

echo "=== 3. Python packages ==="
pip3 install --break-system-packages \
    pyTelegramBotAPI \
    fastapi "uvicorn[standard]" \
    faster-whisper \
    vosk \
    pyaudio \
    psycopg[binary] psycopg-pool pgvector psycopg2-binary \
    python-multipart jinja2 aiofiles \
    requests httpx \
    bcrypt PyJWT \
    fastembed \
    pymupdf python-docx \
    pyyaml jsonschema \
    openai \
    sqlite-vec \
    google-api-python-client google-auth-httplib2 google-auth-oauthlib \
    scipy cryptography \
    playwright

python3 -m playwright install chromium

echo "=== 4. Taris directory structure ==="
mkdir -p "$TARIS_DIR"/{web/templates,web/static,piper,tests/voice/results,core,features,telegram}

echo "=== 5. Systemd user services ==="
mkdir -p ~/.config/systemd/user/
CONF_DIR="$SCRIPT_DIR/../../system-configs/taristation2/systemd/user"
for svc in taris-telegram.service taris-web.service taris-voice.service taris-tunnel.service ollama.service; do
    cp "$CONF_DIR/$svc" ~/.config/systemd/user/
done
systemctl --user daemon-reload
systemctl --user enable taris-telegram taris-web taris-tunnel

echo "=== 6. PostgreSQL (local) ==="
sudo -u postgres psql <<'SQL'
CREATE USER taris_user WITH PASSWORD 'CHANGE_ME';
CREATE DATABASE taris_db OWNER taris_user;
\c taris_db
CREATE EXTENSION IF NOT EXISTS vector;
SQL

echo "=== 7. SSH tunnel key for VPS ==="
if [ ! -f ~/.ssh/vps_tunnel_key ]; then
    ssh-keygen -t ed25519 -f ~/.ssh/vps_tunnel_key -N "" -C "taristation2-vps-tunnel"
    echo "  → Add ~/.ssh/vps_tunnel_key.pub to VPS authorized_keys"
    cat ~/.ssh/vps_tunnel_key.pub
fi

echo "=== 8. bot.env ==="
if [ ! -f "$TARIS_DIR/bot.env" ]; then
    cp "$SCRIPT_DIR/../../system-configs/taristation2/bot.env.template" "$TARIS_DIR/bot.env"
    echo "  → EDIT $TARIS_DIR/bot.env — fill all CHANGE_ME values"
fi

echo ""
echo "=== Setup complete ==="
echo "Next steps:"
echo "  1. Edit ~/.taris/bot.env (fill CHANGE_ME)"
echo "  2. rsync -av --exclude='*.pyc' src/ ~/.taris/"
echo "  3. systemctl --user start taris-telegram taris-web"
echo "  4. journalctl --user-unit=taris-web -f"
