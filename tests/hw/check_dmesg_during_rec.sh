#!/bin/bash
echo "=== Kernel messages (last 10 lines) before test ==="
dmesg | tail -5

echo ""
echo "=== Starting arecord briefly ==="
timeout 2 arecord -D hw:2,0 -f S16_LE -r 48000 -c 1 /tmp/err_test.wav 2>&1 &
AREC_PID=$!
sleep 0.5
echo "=== New kernel messages during recording ==="
dmesg | tail -10
wait $AREC_PID

echo ""
echo "=== USB error registers ==="
cat /sys/kernel/debug/usb/usbmon/1u 2>/dev/null | head -5 || echo "usbmon not accessible"

echo ""
echo "=== USB device stats ==="
cat /sys/bus/usb/devices/1-1.2/power/autosuspend_delay_ms 2>/dev/null
echo "USB power mgmt: $(cat /sys/bus/usb/devices/1-1.2/power/control 2>/dev/null)"
echo "USB level: $(cat /sys/bus/usb/devices/1-1.2/power/level 2>/dev/null)"
echo "USB runtime_status: $(cat /sys/bus/usb/devices/1-1.2/power/runtime_status 2>/dev/null)"
ls /sys/bus/usb/devices/1-1.2/ | head -20
