#!/bin/bash
# Try reloading snd-usb-audio with device_setup for webcam
# This requires briefly stopping PipeWire

echo "=== Stopping PipeWire/WirePlumber temporarily ==="
systemctl --user stop wireplumber pipewire 2>/dev/null
sleep 1

echo "=== Unloading snd-usb-audio ==="
rmmod snd-usb-audio 2>/dev/null && echo "Unloaded" || echo "Could not unload"

echo "=== Reloading with device_setup=0x01 for card index 2 ==="
# index param sets which card slot to use
# device_setup=1 enables SET_FORMAT for many Philips-like devices
modprobe snd-usb-audio "index=2" "device_setup=1" 2>/dev/null
sleep 1

echo "=== Restarting PipeWire ==="
systemctl --user start pipewire wireplumber 2>/dev/null
sleep 2

export XDG_RUNTIME_DIR=/run/user/1000
echo "=== Testing audio capture ==="
timeout 3 pw-record \
    --target alsa_input.usb-0471_USB_Video_Camera-02.mono-fallback \
    /tmp/audio_quirk_test.wav 2>&1
echo "EXIT: $?"
ls -lh /tmp/audio_quirk_test.wav 2>/dev/null

echo "=== Stream status after fix ==="
cat /proc/asound/card2/stream0 2>/dev/null | grep -E 'Packet|freq|Altset|Status'
