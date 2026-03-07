#!/bin/bash
# Try implicit_fb fix for USB audio on Pi 3 DWC_OTG
# Reference: https://wiki.archlinux.org/title/USB_audio

echo "=== Stopping PipeWire ==="
systemctl --user stop wireplumber pipewire-pulse pipewire 2>/dev/null
sleep 2

echo "=== Reloading snd-usb-audio with implicit_fb=1 for the USB webcam ==="
# Unload
rmmod snd-usb-audio 2>/dev/null
sleep 1

# Reload with implicit feedback enabled for card slot 2
# index=2 selects slot 2 (our webcam occupies card 2)
# It's tricky to target one specific device — try global implicit_fb first
modprobe snd-usb-audio implicit_fb=1 2>&1
echo "modprobe exit: $?"
sleep 1

echo "=== Test arecord directly ==="
timeout 3 arecord -D hw:2,0 -f S16_LE -r 48000 -c 1 /tmp/test_implicit.wav 2>&1
echo "arecord EXIT: $?"
ls -lh /tmp/test_implicit.wav 2>/dev/null

echo ""
echo "=== PCM status ==="
cat /proc/asound/card2/pcm0c/sub0/status 2>/dev/null | head -5
cat /proc/asound/card2/stream0 2>/dev/null | grep -E 'Packet|freq|Altset|Status'

echo ""
echo "=== Restarting PipeWire ==="
systemctl --user start pipewire 2>/dev/null
sleep 1
systemctl --user start pipewire-pulse wireplumber 2>/dev/null
sleep 2

export XDG_RUNTIME_DIR=/run/user/1000
echo "=== PipeWire test after fix ==="
timeout 3 pw-record \
    --target alsa_input.usb-0471_USB_Video_Camera-02.mono-fallback \
    /tmp/test_pw_after_fix.wav 2>/dev/null
ls -lh /tmp/test_pw_after_fix.wav 2>/dev/null

pactl list sources short 2>/dev/null | grep Camera
