#!/bin/bash
echo "=== Stopping PipeWire to test ALSA direct ==="
systemctl --user stop wireplumber pipewire-pulse pipewire 2>/dev/null
sleep 2

echo "=== Testing arecord direct on hw:2,0 ==="
timeout 3 arecord -D hw:2,0 -f S16_LE -r 48000 -c 1 \
    /tmp/arecord_direct.wav 2>&1
echo "arecord EXIT: $?"
ls -lh /tmp/arecord_direct.wav 2>/dev/null

echo ""
echo "=== Try with plughw ==="
timeout 3 arecord -D plughw:2,0 -f S16_LE -r 16000 -c 1 \
    /tmp/arecord_plug.wav 2>&1
echo "arecord plughw EXIT: $?"
ls -lh /tmp/arecord_plug.wav 2>/dev/null

echo ""
echo "=== PCM status during hw:2,0 capture ==="
timeout 3 arecord -D hw:2,0 -f S16_LE -r 48000 -c 1 \
    /tmp/arecord_check.wav &
AREC_PID=$!
sleep 1
cat /proc/asound/card2/pcm0c/sub0/status 2>/dev/null
wait $AREC_PID

echo ""
echo "=== Restarting PipeWire ==="
systemctl --user start pipewire 2>/dev/null
sleep 1
systemctl --user start pipewire-pulse wireplumber 2>/dev/null
echo "PipeWire restarted"
