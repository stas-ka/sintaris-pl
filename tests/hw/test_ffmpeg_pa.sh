#!/bin/bash
export XDG_RUNTIME_DIR=/run/user/1000
export PULSE_SERVER=unix:/run/user/1000/pulse/native

echo "=== ffmpeg PulseAudio capture, 3 seconds ==="
ffmpeg -f pulse \
    -i alsa_input.usb-0471_USB_Video_Camera-02.mono-fallback \
    -ar 16000 -ac 1 \
    -t 3 /tmp/ffmpeg_pa.wav -y 2>&1 | grep -E 'Error|error|Input|Output|audio|size|time'
echo "EXIT: $?"
ls -lh /tmp/ffmpeg_pa.wav 2>/dev/null || echo "No file created"

echo ""
echo "=== Check node state ==="
pactl list sources short | grep Camera
