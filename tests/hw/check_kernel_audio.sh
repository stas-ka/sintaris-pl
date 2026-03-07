#!/bin/bash
export XDG_RUNTIME_DIR=/run/user/1000

echo "=== Starting pw-record in background ==="
timeout 5 pw-record \
    --target alsa_input.usb-0471_USB_Video_Camera-02.mono-fallback \
    /tmp/audio_kern_test.wav &
PW_PID=$!

# Check PCM status WHILE recording
sleep 1
echo "=== PCM capture status during recording ==="
cat /proc/asound/card2/pcm0c/sub0/status 2>/dev/null || echo "PCM capture not open"
echo ""
echo "=== PCM hw_params ==="
cat /proc/asound/card2/pcm0c/sub0/hw_params 2>/dev/null || echo "No hw_params"

sleep 2
# Check new dmesg messages
echo ""
echo "=== New kernel messages ==="
dmesg | grep -E 'usb|sound|snd|pcm|urb' | tail -5

wait $PW_PID

echo ""
echo "=== Audio file result ==="
ls -lh /tmp/audio_kern_test.wav 2>/dev/null
