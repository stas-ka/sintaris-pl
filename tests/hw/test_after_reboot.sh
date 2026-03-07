#!/bin/bash
export XDG_RUNTIME_DIR=/run/user/1000

echo "=== ALSA cards after reboot ==="
arecord -l 2>&1

echo ""
echo "=== snd-usb-audio implicit_fb per slot ==="
cat /sys/module/snd_usb_audio/parameters/implicit_fb

echo ""
echo "=== Webcam card info ==="
arecord -l | grep -i camera

echo ""
echo "=== Test arecord direct on hw:2,0 ==="
timeout 3 arecord -D hw:2,0 -f S16_LE -r 16000 -c 1 /tmp/test_reboot.wav 2>&1
echo "EXIT: $?"
ls -lh /tmp/test_reboot.wav 2>/dev/null

echo ""
echo "=== PipeWire PulseAudio sources ==="
pactl list sources short 2>/dev/null | grep -v monitor

echo ""
echo "=== pw-record test ==="
timeout 3 pw-record \
    --target alsa_input.usb-0471_USB_Video_Camera-02.mono-fallback \
    /tmp/test_pw_reboot.wav 2>/dev/null
ls -lh /tmp/test_pw_reboot.wav 2>/dev/null
