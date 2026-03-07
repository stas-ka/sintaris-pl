#!/bin/bash
export XDG_RUNTIME_DIR=/run/user/1000

echo "=== Start recording ==="
timeout 5 pw-record \
    --target alsa_input.usb-0471_USB_Video_Camera-02.mono-fallback \
    /tmp/audio_xrun_test.wav &
PW_PID=$!
sleep 2

echo "=== PCM status mid-recording ==="
cat /proc/asound/card2/pcm0c/sub0/status 2>/dev/null

echo ""
echo "=== PCM info ==="
cat /proc/asound/card2/pcm0c/sub0/info 2>/dev/null

echo ""
echo "=== USB endpoint details ==="
cat /sys/kernel/debug/usb/devices 2>/dev/null | grep -A5 "4710334\|0471/0334" | head -20 || echo "no debug"

echo ""
echo "=== Checking alternate interfaces ==="
cat /sys/bus/usb/devices/1-1.2/1-1.2\:1.3/bAlternateSetting 2>/dev/null || echo "Can't read altset"
cat /sys/bus/usb/devices/1-1.2:1.3/bAlternateSetting 2>/dev/null || echo "Device path issue"

echo ""
# Try checking the USB bandwidth allocation
cat /sys/bus/usb/devices/usb1/../bandwidth 2>/dev/null || echo "no bandwidth file"
cat /sys/devices/platform/soc/3f980000.usb/usb1/1-1/1-1.2/1-1.2:1.3/bAlternateSetting 2>/dev/null || echo "altset not found"

wait $PW_PID

echo ""
echo "FINAL: $(ls -lh /tmp/audio_xrun_test.wav 2>/dev/null)"
