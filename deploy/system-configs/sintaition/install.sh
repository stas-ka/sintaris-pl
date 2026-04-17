#!/usr/bin/env bash
# install-sintaition.sh — Initial setup for SintAItion (TariStation1 OpenClaw)
#
# Target:   Ubuntu 24.04 LTS, AMD Radeon 890M GPU (ROCm), 48GB RAM, 915GB NVMe
# Services: Telegram bot, Web UI, Voice assistant, Ollama LLM (GPU), SSH tunnels
# Run as:   stas (user with sudo)
# Usage:    bash install-sintaition.sh
#
# Prerequisites:
#   - Ubuntu 24.04 LTS installed with user 'stas'
#   - Internet access
#   - SSH key pair generated: ssh-keygen -t ed25519 -f ~/.ssh/vps_tunnel_key
#   - VPS public key added to VPS authorized_keys
#   - bot.env filled in (copy from bot.env.template, fill CHANGE_ME fields)

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
    pipewire pipewire-pulse \
    x11vnc \
    nginx

echo "=== 2. ROCm (AMD GPU for Ollama) ==="
# Install ROCm 6.x for gfx1150 (Radeon 890M)
wget -q https://repo.radeon.com/amdgpu-install/6.3.3/ubuntu/noble/amdgpu-install_6.3.3.60303-1_all.deb
sudo dpkg -i amdgpu-install_6.3.3.60303-1_all.deb
sudo amdgpu-install --usecase=rocm --no-dkms -y
sudo usermod -aG render,video stas
echo "=== ROCm installed — GPU accel requires re-login or reboot ==="

echo "=== 3. Ollama ==="
curl -fsSL https://ollama.com/install.sh | sh
# Pull required models
ollama pull gemma4:e4b      # primary (AMD GPU, 5GB)
# ollama pull gemma4:e2b    # lighter alternative (3.2GB)

echo "=== 4. Python packages ==="
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

echo "=== 5. Taris directory structure ==="
mkdir -p "$TARIS_DIR"/{web/templates,web/static,piper,tests/voice/results,core,features,telegram}

echo "=== 6. Deploy taris from source ==="
# Run from project root:
# rsync -av --exclude='*.pyc' --exclude='__pycache__' src/ ~/.taris/
echo "  → Copy src/ to ~/.taris/ (run from project root)"
echo "  → rsync -av --exclude='*.pyc' src/ ~/.taris/"

echo "=== 7. Systemd user services ==="
mkdir -p ~/.config/systemd/user/
CONF_DIR="$SCRIPT_DIR/../../system-configs/sintaition/systemd/user"
for svc in taris-telegram.service taris-web.service taris-voice.service taris-tunnel.service taris-pg-tunnel.service ollama.service; do
    cp "$CONF_DIR/$svc" ~/.config/systemd/user/
done
systemctl --user daemon-reload
systemctl --user enable taris-telegram taris-web taris-tunnel taris-pg-tunnel
# taris-voice and ollama: enable manually after testing

echo "=== 8. System-level Ollama service (with AMD GPU) ==="
sudo cp "$SCRIPT_DIR/../../system-configs/sintaition/systemd/system/ollama.service" \
    /etc/systemd/system/ollama.service
sudo systemctl daemon-reload
sudo systemctl enable ollama
sudo systemctl start ollama

echo "=== 9. IPv4 preference (AMD ROCm / Ollama pull fix) ==="
sudo cp "$SCRIPT_DIR/../../system-configs/sintaition/etc/gai.conf" /etc/gai.conf

echo "=== 10. PostgreSQL (local) — configure DB and user ==="
# postgresql was already installed in step 1
sudo -u postgres psql <<'SQL'
CREATE USER taris_user WITH PASSWORD 'CHANGE_ME';
CREATE DATABASE taris_db OWNER taris_user;
\c taris_db
CREATE EXTENSION IF NOT EXISTS vector;
SQL
echo "  → Remember to set actual password in both PostgreSQL and bot.env"

echo "=== 11. SSH tunnel key for VPS ==="
if [ ! -f ~/.ssh/vps_tunnel_key ]; then
    ssh-keygen -t ed25519 -f ~/.ssh/vps_tunnel_key -N "" -C "sintaition-vps-tunnel"
    echo "  → Add ~/.ssh/vps_tunnel_key.pub to VPS authorized_keys:"
    cat ~/.ssh/vps_tunnel_key.pub
fi

echo "=== 12. bot.env ==="
if [ ! -f "$TARIS_DIR/bot.env" ]; then
    cp "$SCRIPT_DIR/../../system-configs/sintaition/bot.env.template" "$TARIS_DIR/bot.env"
    echo "  → EDIT $TARIS_DIR/bot.env — fill all CHANGE_ME values before starting services"
else
    echo "  → bot.env already exists — verify it is up to date"
fi

echo ""
echo "=== Setup complete ==="
echo "Next steps:"
echo "  1. Edit ~/.taris/bot.env (fill CHANGE_ME)"
echo "  2. Copy source files: rsync -av --exclude='*.pyc' src/ ~/.taris/"
echo "  3. systemctl --user start taris-telegram taris-web"
echo "  4. journalctl --user-unit=taris-web -f"
echo "  5. Test: curl http://localhost:8080/"
echo "  6. Verify SSH tunnel: journalctl --user-unit=taris-tunnel -f"
