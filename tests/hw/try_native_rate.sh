#!/bin/bash
export XDG_RUNTIME_DIR=/run/user/1000

echo "=== Check if usbmon is available ==="
ls /sys/kernel/debug/usb/usbmon/ 2>/dev/null || modprobe usbmon 2>/dev/null
ls /sys/kernel/debug/usb/usbmon/ 2>/dev/null || echo "usbmon not available"

echo ""
echo "=== Trying to capture with explicit 16000Hz (native rate) ==="
# Try different approach: use pw-record WITHOUT upsampling (device's native rate)
# and see if small rate differences cause the issue
timeout 3 pw-record \
    --target alsa_input.usb-0471_USB_Video_Camera-02.mono-fallback \
    --rate=16000 \
    /tmp/audio_16k.wav &
PW_PID=$!
sleep 1
echo "PCM status at 16kHz request:"
cat /proc/asound/card2/pcm0c/sub0/status 2>/dev/null | grep -E 'state|hw_ptr|avail_max|rate'
wait $PW_PID
ls -lh /tmp/audio_16k.wav 2>/dev/null

echo ""
echo "=== Now trying with pw-record using no target (default source test) ==="
# Force default source to be the webcam
wpctl set-default 84

timeout 3 pw-record /tmp/audio_default.wav &
PW_PID=$!
sleep 1
echo "PCM status with default source:"
cat /proc/asound/card2/pcm0c/sub0/status 2>/dev/null | grep -E 'state|hw_ptr|avail_max'
wait $PW_PID
ls -lh /tmp/audio_default.wav 2>/dev/null

echo ""
echo "=== Check if there's a MMAP vs read mode issue ==="
# The PCM was opened as MMAP_INTERLEAVED - check if switching to read mode helps
# This is done via snd-usb-audio module parameter
cat /sys/module/snd_usb_audio/parameters/use_vmalloc 2>/dev/null
