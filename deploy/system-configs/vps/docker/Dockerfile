# Taris OpenClaw — Docker image for VPS deployment (aarch64 / linux/arm64)
#
# Build context: /opt/taris-docker/
# Source code:   mounted from /opt/taris-docker/app/ at runtime
# Data:          /opt/taris-docker/data/ (whisper cache, piper models)
#
# Usage (in /opt/taris-docker/):
#   docker build -t taris-vps .
#   docker compose up -d

FROM python:3.12-slim

# System packages: ffmpeg for audio encoding/decoding, libopus for OGG
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libopus0 \
        libsndfile1 \
        && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (separate layer for build cache)
COPY requirements.docker.txt /tmp/requirements.docker.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /tmp/requirements.docker.txt

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Source code is mounted at runtime via docker-compose volume
# Default CMD is overridden per-service in docker-compose.yml
CMD ["python3", "telegram_menu_bot.py"]
