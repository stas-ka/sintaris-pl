#!/bin/bash
export XDG_RUNTIME_DIR=/run/user/1000
export PIPEWIRE_RUNTIME_DIR=/run/user/1000
export PULSE_SERVER=unix:/run/user/1000/pulse/native
echo "=== Testing Piper TTS ==="
echo "Привет, я Пико. Готов помочь." | /usr/local/bin/piper \
    --model /home/stas/.taris/ru_RU-irina-medium.onnx \
    --output-raw 2>/tmp/piper_err.txt | aplay --rate=22050 --format=S16_LE --channels=1 - 2>&1
EXIT=$?
echo "Exit code: $EXIT"
if [ -s /tmp/piper_err.txt ]; then
    echo "=== Piper stderr ==="
    cat /tmp/piper_err.txt
fi
