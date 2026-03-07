#!/bin/bash
export XDG_RUNTIME_DIR=/run/user/1000

echo "=== Testing with audio using ignore_ctl_error ==="
# Check if we can temporarily reload snd-usb-audio with different parameters
# But with PipeWire running, we can't easily unload the module. 
# Instead, test if quirks help.

echo "Current snd-usb-audio module parameters:"
ls /sys/module/snd_usb_audio/parameters/ 2>/dev/null | while read p; do
    echo "  $p = $(cat /sys/module/snd_usb_audio/parameters/$p 2>/dev/null)"
done

echo ""
echo "=== Checking USB audio urb stats ==="
# Check current USB stats
cat /proc/asound/card2/stream0 2>/dev/null | head -30 || echo "No stream0"

echo ""
echo "=== Starting recording and check stream stats ==="
timeout 3 pw-record \
    --target alsa_input.usb-0471_USB_Video_Camera-02.mono-fallback \
    /tmp/audio_stats_test.wav &
PW_PID=$!
sleep 1

echo "Stream during capture:"
cat /proc/asound/card2/stream0 2>/dev/null | head -30 || echo "No stream0 during capture"

wait $PW_PID
echo ""
echo "Audio file: $(ls -lh /tmp/audio_stats_test.wav 2>/dev/null)"

echo ""
echo "=== dmesg USB errors ==="
dmesg | grep -i '1-1.2\|1-1.1.2\|error\|urb\|ENODEV\|timeout' | grep -v 'UVC\|snd-usb\|uvcvideo' | tail -10
