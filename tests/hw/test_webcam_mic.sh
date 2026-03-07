#!/bin/bash
# Test webcam microphone recording via PipeWire
export XDG_RUNTIME_DIR=/run/user/1000
export PIPEWIRE_RUNTIME_DIR=/run/user/1000

WEBCAM_NODE="alsa_input.usb-0471_USB_Video_Camera-02.mono-fallback"

echo "=== PulseAudio/PipeWire info ==="
pactl info 2>&1 | head -3

echo ""
echo "=== Available audio sources ==="
pactl list sources short 2>&1

echo ""
echo "=== Testing pw-record for 3 seconds ==="
timeout 3 pw-record \
  --target "$WEBCAM_NODE" \
  --rate=16000 --channels=1 --format=s16 \
  - 2>/tmp/pwrec_err.txt | wc -c
echo "pw-record stderr: $(cat /tmp/pwrec_err.txt)"

echo ""
echo "=== Testing parec for 3 seconds ==="
timeout 3 parec \
  --rate=16000 --channels=1 --format=s16le \
  --device="$WEBCAM_NODE" \
  - 2>/tmp/parec_err.txt | wc -c
echo "parec stderr: $(cat /tmp/parec_err.txt)"

echo ""
echo "=== Current node state ==="
pactl list sources | grep -A3 "USB Video Camera"
