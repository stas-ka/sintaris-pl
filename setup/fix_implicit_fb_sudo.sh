#!/bin/bash
# Fix USB audio on Pi 3 - must be run as stas with sudo access
# Set HOSTPWD env var before running, or pass password as first arg:
#   HOSTPWD=yourpass bash fix_implicit_fb_sudo.sh
#   bash fix_implicit_fb_sudo.sh yourpass
# The HOSTPWD variable is normally loaded from .env (gitignored).
PASS="${1:-${HOSTPWD:-}}"
if [[ -z "$PASS" ]]; then
  read -sp "Pi sudo password: " PASS; echo
fi

echo "=== Writing modprobe config ==="
echo "options snd-usb-audio implicit_fb=1" > /tmp/usb-audio-fix.conf
echo $PASS | sudo -S cp /tmp/usb-audio-fix.conf /etc/modprobe.d/usb-audio-fix.conf
echo "Config: $(cat /etc/modprobe.d/usb-audio-fix.conf 2>/dev/null)"

echo ""
echo "=== Stopping PipeWire ==="
systemctl --user stop wireplumber pipewire-pulse pipewire 2>/dev/null
sleep 2

echo "=== Reloading snd-usb-audio as root ==="
echo $PASS | sudo -S rmmod snd-usb-audio 2>&1
sleep 1
echo $PASS | sudo -S modprobe snd-usb-audio 2>&1
sleep 1

echo "=== Check implicit_fb parameter ==="
cat /sys/module/snd_usb_audio/parameters/implicit_fb 2>/dev/null

echo ""
echo "=== Stream info after reload ==="
cat /proc/asound/card2/stream0 2>/dev/null | grep -E 'Status|Packet|freq|Altset' | head -5

echo ""
echo "=== Test arecord directly ==="
timeout 3 arecord -D hw:2,0 -f S16_LE -r 48000 -c 1 /tmp/test_fixed.wav 2>&1
echo "EXIT: $?"
ls -lh /tmp/test_fixed.wav 2>/dev/null

echo ""
echo "=== Restarting PipeWire ==="
systemctl --user start pipewire && sleep 1
systemctl --user start pipewire-pulse wireplumber
sleep 2

export XDG_RUNTIME_DIR=/run/user/1000
echo "=== PipeWire test after fix ==="
timeout 3 pw-record \
    --target alsa_input.usb-0471_USB_Video_Camera-02.mono-fallback \
    /tmp/test_pw_fixed.wav 2>/dev/null
ls -lh /tmp/test_pw_fixed.wav 2>/dev/null
pactl list sources short 2>/dev/null | grep Camera
