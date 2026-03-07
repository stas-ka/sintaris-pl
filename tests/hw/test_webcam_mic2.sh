#!/bin/bash
# Webcam mic test - fixes XDG_RUNTIME_DIR for PipeWire access
export XDG_RUNTIME_DIR=/run/user/1000
export PIPEWIRE_RUNTIME_DIR=/run/user/1000

WEBCAM_NODE="alsa_input.usb-0471_USB_Video_Camera-02.mono-fallback"

echo "XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR"
echo "pw-record test: 3 seconds to /tmp/audio_test.wav"

timeout 3 pw-record \
    --target "$WEBCAM_NODE" \
    /tmp/audio_test.wav 2>&1
echo "EXIT: $?"
ls -lh /tmp/audio_test.wav 2>/dev/null || echo "File not created"

echo ""
echo "parec test: 3 seconds"
timeout 3 parec \
    --rate=16000 --channels=1 --format=s16le \
    --device="$WEBCAM_NODE" \
    /tmp/parec_test.raw 2>&1
echo "EXIT: $?"
ls -lh /tmp/parec_test.raw 2>/dev/null || echo "File not created"
