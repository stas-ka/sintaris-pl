#!/bin/bash
export XDG_RUNTIME_DIR=/run/user/1000

# Start pw-record in background and check WirePlumber logs simultaneously
echo "=== WirePlumber journal before recording ==="
journalctl --user -u wireplumber --since "30 seconds ago" --no-pager 2>/dev/null | tail -5

echo ""
echo "=== Starting pw-record for 3 seconds ==="
timeout 3 pw-record \
    --target alsa_input.usb-0471_USB_Video_Camera-02.mono-fallback \
    /tmp/audio_test2.wav &
PW_PID=$!

# Check WirePlumber logs while recording
sleep 1
echo "=== WirePlumber logs during recording ==="
journalctl --user -u wireplumber --since "5 seconds ago" --no-pager 2>/dev/null | tail -10

sleep 3
wait $PW_PID 2>/dev/null

echo ""
echo "=== Result ==="
ls -lh /tmp/audio_test2.wav 2>/dev/null

echo ""
echo "=== WirePlumber logs after recording ==="
journalctl --user -u wireplumber --since "10 seconds ago" --no-pager 2>/dev/null | tail -10

echo ""
echo "=== PipeWire node status during potential recording ==="
pw-cli info 84 2>/dev/null | head -10
