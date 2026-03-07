#!/bin/bash
export XDG_RUNTIME_DIR=/run/user/1000

echo "=== ffmpeg capture test (3 seconds) ==="
# Try alsalib direct first
ffmpeg -f alsa -i hw:2,0 -t 3 /tmp/ffmpeg_test.wav -y 2>&1 | tail -5
echo "ALSA direct EXIT: $?"
ls -lh /tmp/ffmpeg_test.wav 2>/dev/null

echo ""
echo "=== ffmpeg via PulseAudio ==="
ffmpeg -f pulse -i alsa_input.usb-0471_USB_Video_Camera-02.mono-fallback \
    -t 3 /tmp/ffmpeg_pulse_test.wav -y 2>&1 | tail -5
echo "PULSE EXIT: $?"
ls -lh /tmp/ffmpeg_pulse_test.wav 2>/dev/null

echo ""
echo "=== ffmpeg via v4l2+alsa simultaneous ==="
ffmpeg -f v4l2 -i /dev/video0 \
    -f alsa -i hw:2,0 \
    -t 3 -vcodec copy -acodec pcm_s16le \
    /tmp/ffmpeg_both.avi -y 2>&1 | tail -5
echo "V4L2+ALSA EXIT: $?"
ls -lh /tmp/ffmpeg_both.avi 2>/dev/null
