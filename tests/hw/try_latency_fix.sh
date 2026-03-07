#!/bin/bash
# Targeted fix for USB audio on Pi 3 (dwc_otg)
# Tests: lowlatency=N, different period sizes, quirk flags

echo "=== Current snd-usb-audio lowlatency ==="
cat /sys/module/snd_usb_audio/parameters/lowlatency

export XDG_RUNTIME_DIR=/run/user/1000

echo ""
echo "=== Trying quirk_flags override ==="
# quirk_flags=0x5800000 enables sync_ep_only + implicit_fb
# These are bitmask values from sound/usb/quirks.h
# bit 0x0400000 = implicit_fb
# bit 0x1000000 = sync_ep_only

# First, check if we can try a different approach using  
# alsa-piped with specific period time
# pw-record with explicit period time to reduce MMAP issues

echo ""
echo "=== Try pw-record with different latency ==="
for lat in 50 100 500 1000; do
    rm -f /tmp/audio_lat_$lat.wav 2>/dev/null
    timeout 3 pw-record \
        --target alsa_input.usb-0471_USB_Video_Camera-02.mono-fallback \
        --latency=${lat}ms \
        /tmp/audio_lat_$lat.wav 2>/dev/null
    SIZE=$(stat -c %s /tmp/audio_lat_$lat.wav 2>/dev/null || echo 0)
    echo "Latency ${lat}ms: file size = $SIZE bytes"
done

echo ""
echo "=== Try with pw-cat instead of pw-record ==="
timeout 3 pw-cat --capture \
    --target alsa_input.usb-0471_USB_Video_Camera-02.mono-fallback \
    /tmp/audio_pwcat.wav 2>&1 | tail -3
echo "pw-cat EXIT: $?"
ls -lh /tmp/audio_pwcat.wav 2>/dev/null

echo ""
echo "=== Try with no resampling (native format) ==="
# Force 48000Hz output to avoid any SRC
timeout 3 pw-record \
    --target alsa_input.usb-0471_USB_Video_Camera-02.mono-fallback \
    --rate=48000 --channels=1 --format=s16 \
    /tmp/audio_native.wav 2>/dev/null
SIZE=$(stat -c %s /tmp/audio_native.wav 2>/dev/null || echo 0)  
echo "Native 48kHz: file size = $SIZE bytes"
