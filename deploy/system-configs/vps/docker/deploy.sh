#!/usr/bin/env bash
# deploy-vps-docker.sh — Deploy Taris OpenClaw in Docker on VPS
#
# Run from: Windows dev machine via plink, OR directly on VPS
# Prerequisites: Docker 20+ and Docker Compose V2 installed on VPS
#
# What this script does:
#   1. Create /opt/taris-docker/ directory structure
#   2. Upload Dockerfile + docker-compose.yml from this repo
#   3. Create PostgreSQL database taris_vps (if not exists)
#   4. Upload source code from src/ to /opt/taris-docker/app/
#   5. Copy Piper TTS models from ~/.taris/ to /opt/taris-docker/data/piper/
#   6. Build Docker image taris-vps:latest
#   7. Pre-download faster-whisper base model
#   8. Start containers (telegram + web)
#   9. Create web UI admin account
#  10. Reload nginx with /supertaris-vps/ location
#
# Usage (from dev machine):
#   Set TARIS_SRC to your local src directory
#   Run: bash deploy-vps-docker.sh
#
# Or run directly on VPS:
#   bash /opt/taris-docker/deploy-vps-docker.sh

set -euo pipefail

DOCKER_DIR=/opt/taris-docker
IMAGE_NAME=taris-vps
WEB_ACCOUNT_USER=stas
# WEB_ACCOUNT_PASS set from /opt/taris-docker/bot.env or prompt

echo "=============================="
echo "  Taris VPS Docker Deploy"
echo "=============================="

# ── 1. Directory structure ─────────────────────────────────────────────────────
echo ""
echo "=== 1. Creating /opt/taris-docker/ structure ==="
sudo mkdir -p "$DOCKER_DIR"/{app,data/whisper,data/piper}
sudo chown -R "$USER:$USER" "$DOCKER_DIR"

# ── 2. Dockerfile + docker-compose.yml ────────────────────────────────────────
# These files should already be in $DOCKER_DIR (uploaded by pscp before running this script)
echo "=== 2. Verifying Docker config files ==="
for f in Dockerfile docker-compose.yml requirements.docker.txt; do
    if [ ! -f "$DOCKER_DIR/$f" ]; then
        echo "  ❌ Missing: $DOCKER_DIR/$f — upload with pscp first"
        exit 1
    fi
    echo "  ✓ $f"
done

# ── 3. PostgreSQL database ─────────────────────────────────────────────────────
echo ""
echo "=== 3. PostgreSQL: creating taris_vps database ==="
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname = 'taris_vps'" | grep -q 1 \
    || sudo -u postgres psql -c "CREATE DATABASE taris_vps OWNER taris;"
echo "  ✓ taris_vps database ready"

# ── 4. Source code ─────────────────────────────────────────────────────────────
echo ""
echo "=== 4. Source code (uploaded to $DOCKER_DIR/app/) ==="
if [ "$(ls -A $DOCKER_DIR/app/ 2>/dev/null)" ]; then
    echo "  ✓ Source code present ($(ls $DOCKER_DIR/app/ | wc -l) entries)"
else
    echo "  ⚠️  $DOCKER_DIR/app/ is empty — upload src/ with:"
    echo "     pscp -r -pw \$VPS_PWD src/ stas@dev2null.de:/opt/taris-docker/app/"
    echo "  Continuing (image build may fail if app/ is empty)..."
fi

# ── 5. Piper TTS models ────────────────────────────────────────────────────────
echo ""
echo "=== 5. Piper TTS models ==="
if [ -f "/home/stas/.taris/piper/piper" ]; then
    cp -n /home/stas/.taris/piper/piper "$DOCKER_DIR/data/piper/piper" 2>/dev/null || true
    chmod +x "$DOCKER_DIR/data/piper/piper"
    echo "  ✓ piper binary"
else
    echo "  ⚠️  Piper binary not found at ~/.taris/piper/piper — install_voice.sh first"
fi
for model in /home/stas/.taris/*.onnx /home/stas/.taris/*.onnx.json; do
    [ -f "$model" ] && cp -n "$model" "$DOCKER_DIR/data/piper/" 2>/dev/null || true
done
ls "$DOCKER_DIR/data/piper/" && echo "  ✓ piper models present"

# ── 6. Build Docker image ──────────────────────────────────────────────────────
echo ""
echo "=== 6. Building Docker image taris-vps:latest ==="
echo "    (first build may take 5-15 minutes on VPS ARM64)"
docker build -t "$IMAGE_NAME" "$DOCKER_DIR"
echo "  ✓ Image built"

# ── 7. Pre-download faster-whisper model ──────────────────────────────────────
echo ""
echo "=== 7. Pre-downloading faster-whisper base model ==="
WHISPER_MODEL=${FASTER_WHISPER_MODEL:-base}
docker run --rm \
    -v "$DOCKER_DIR/data/whisper:/root/.cache/huggingface" \
    "$IMAGE_NAME" \
    python3 -c "
import os; os.environ['TRANSFORMERS_OFFLINE']='0'
from faster_whisper import WhisperModel
print('Downloading model: $WHISPER_MODEL ...')
WhisperModel('$WHISPER_MODEL', device='cpu', compute_type='int8', download_root='/root/.cache/huggingface')
print('Done!')
"
echo "  ✓ Whisper model cached"

# ── 8. bot.env ────────────────────────────────────────────────────────────────
echo ""
echo "=== 8. bot.env ==="
if [ ! -f "$DOCKER_DIR/bot.env" ]; then
    cp "$DOCKER_DIR/app/deploy/system-configs/vps/docker/bot.env.template" "$DOCKER_DIR/bot.env"
    echo "  ⚠️  Created $DOCKER_DIR/bot.env from template"
    echo "  ⚠️  REQUIRED: Edit bot.env and fill in:"
    echo "     - BOT_TOKEN (from @BotFather for Supertariss bot)"
    echo "     - ALLOWED_USERS + ADMIN_USERS (Telegram user IDs)"
    echo "     - OPENAI_API_KEY (from platform.openai.com)"
    echo "     - STORE_PG_DSN password (taris user password)"
    echo "  Press Enter when bot.env is ready, Ctrl+C to abort..."
    read -r
else
    echo "  ✓ $DOCKER_DIR/bot.env exists"
fi

# Verify BOT_TOKEN is set
TOKEN_VAL=$(grep '^BOT_TOKEN=' "$DOCKER_DIR/bot.env" | cut -d= -f2)
if [ "$TOKEN_VAL" = "CHANGE_ME" ] || [ -z "$TOKEN_VAL" ]; then
    echo "  ⚠️  WARNING: BOT_TOKEN is not set — Telegram bot will not work"
    echo "  Set it in $DOCKER_DIR/bot.env and run: docker restart taris-vps-telegram"
fi

# ── 9. Start containers ────────────────────────────────────────────────────────
echo ""
echo "=== 9. Starting containers ==="
cd "$DOCKER_DIR" && docker compose up -d
sleep 5
docker ps | grep taris-vps || echo "  ⚠️  Containers not running — check: docker logs taris-vps-telegram"
echo "  ✓ Containers started"

# ── 10. Web UI admin account ──────────────────────────────────────────────────
echo ""
echo "=== 10. Web UI admin account ==="
PG_DSN=$(grep '^STORE_PG_DSN=' "$DOCKER_DIR/bot.env" | cut -d= -f2-)
if [[ "$PG_DSN" != *"CHANGE_ME"* ]]; then
    # Generate bcrypt hash for password 'buerger'
    HASH=$(docker run --rm "$IMAGE_NAME" python3 -c "
import bcrypt, sys
pw = 'buerger'
h = bcrypt.hashpw(pw.encode(), bcrypt.gensalt(rounds=12)).decode()
print(h)
")
    docker run --rm \
        --env-file "$DOCKER_DIR/bot.env" \
        "$IMAGE_NAME" \
        python3 -c "
import psycopg, os
dsn = os.environ['STORE_PG_DSN']
with psycopg.connect(dsn) as conn:
    conn.execute('''
        CREATE TABLE IF NOT EXISTS web_accounts (
            username TEXT PRIMARY KEY,
            pw_hash  TEXT NOT NULL,
            role     TEXT NOT NULL DEFAULT 'user'
        )
    ''')
    conn.execute('''
        INSERT INTO web_accounts (username, pw_hash, role)
        VALUES ('stas', '${HASH}', 'admin')
        ON CONFLICT (username) DO UPDATE SET pw_hash = EXCLUDED.pw_hash, role = 'admin'
    ''')
    conn.commit()
print('Web account stas (admin) created/updated, password: buerger')
"
    echo "  ✓ Web account: stas / buerger (admin)"
else
    echo "  ⚠️  STORE_PG_DSN not configured — web account not created"
    echo "  Run manually after setting bot.env"
fi

# ── 11. nginx ──────────────────────────────────────────────────────────────────
echo ""
echo "=== 11. nginx reload ==="
sudo nginx -t && sudo systemctl reload nginx
echo "  ✓ nginx reloaded"

echo ""
echo "=============================="
echo "  DONE"
echo "=============================="
echo ""
echo "Web UI:    https://agents.sintaris.net/supertaris-vps/"
echo "Login:     stas / buerger"
echo ""
echo "Container logs:"
echo "  docker logs -f taris-vps-telegram"
echo "  docker logs -f taris-vps-web"
echo ""
if [ "$TOKEN_VAL" = "CHANGE_ME" ] || [ -z "$TOKEN_VAL" ]; then
    echo "⚠️  NEXT STEPS:"
    echo "  1. Create Supertariss bot via @BotFather on Telegram"
    echo "  2. Edit /opt/taris-docker/bot.env — set BOT_TOKEN"
    echo "  3. docker restart taris-vps-telegram"
fi
