#!/bin/bash
# Test if webcam audio works when video is active simultaneously
export XDG_RUNTIME_DIR=/run/user/1000
export PULSE_SERVER=unix:/run/user/1000/pulse/native

echo "=== Starting video stream in background ==="
ffmpeg -f v4l2 -video_size 320x240 -framerate 10 -i /dev/video0 \
    -t 5 /tmp/video_test.mp4 -y >/dev/null 2>&1 &
VIDEO_PID=$!
echo "Video PID: $VIDEO_PID"

# Give video stream a moment to start
sleep 1

echo "=== Recording audio while video is active ==="
timeout 3 pw-record \
    --target alsa_input.usb-0471_USB_Video_Camera-02.mono-fallback \
    /tmp/audio_while_video.wav 2>&1
echo "pw-record EXIT: $?"
ls -lh /tmp/audio_while_video.wav 2>/dev/null

echo ""
echo "=== Checking if pure ALSA works while PipeWire holds the device ==="
# Try to check with arecord but with plughw and a very short test
timeout 2 arecord -D plughw:2,0 -f S16_LE -r 16000 -c 1 \
    /tmp/arecord_test.wav 2>&1
echo "arecord EXIT: $?"  
ls -lh /tmp/arecord_test.wav 2>/dev/null

# Kill video capture  
kill $VIDEO_PID 2>/dev/null
wait $VIDEO_PID 2>/dev/null

echo ""
echo "Video test result:"
ls -lh /tmp/video_test.mp4 2>/dev/null

echo ""
echo "=== Try ffmpeg -f alsa plughw ==="
# Allow ALSA plughw through PipeWire pipewire-alsa? probably not
timeout 3 ffmpeg -f alsa -i plughw:2,0 -ar 16000 -ac 1 \
    -t 3 /tmp/ffmpeg_plughw.wav -y 2>&1 | tail -3
echo "ffmpeg plughw EXIT: $?"
ls -lh /tmp/ffmpeg_plughw.wav 2>/dev/null
