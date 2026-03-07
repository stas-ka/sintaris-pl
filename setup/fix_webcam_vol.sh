#!/bin/bash
# Fix and test webcam mic volume + recording
export XDG_RUNTIME_DIR=/run/user/1000

echo "=== Current webcam mic volume ==="
wpctl get-volume 84

echo ""
echo "=== Setting volume to 100% ==="
wpctl set-volume 84 1.0

echo "=== Volume after set ==="
wpctl get-volume 84

echo ""
echo "=== Test recording 3 seconds to WAV ==="
timeout 3 pw-record \
    --target alsa_input.usb-0471_USB_Video_Camera-02.mono-fallback \
    /tmp/audio_test.wav 2>&1
echo "EXIT: $?"
ls -lh /tmp/audio_test.wav

echo ""
echo "=== Check parec with PA source ==="
timeout 3 parec \
    --rate=16000 --channels=1 --format=s16le \
    --device=alsa_input.usb-0471_USB_Video_Camera-02.mono-fallback \
    /tmp/parec_test.raw 2>&1
echo "EXIT: $?"
ls -lh /tmp/parec_test.raw

echo ""
echo "=== Node state after test ==="
pactl list sources short 2>&1 | grep Camera
