import sounddevice as sd
import numpy as np
import sys

# List all devices
print("All audio devices:")
for i, d in enumerate(sd.query_devices()):
    print(f"  [{i}] {d['name']}  in:{d['max_input_channels']} out:{d['max_output_channels']} rate:{d['default_samplerate']}")
print()

# Find webcam mic by name
webcam_idx = None
for i, d in enumerate(sd.query_devices()):
    name = d['name'].lower()
    if d['max_input_channels'] > 0 and ('usb' in name or 'camera' in name or 'video' in name):
        webcam_idx = i
        break

if webcam_idx is None:
    webcam_idx = sd.default.device[0]
    print(f"No USB mic found, using default input {webcam_idx}")
else:
    print(f"Webcam mic found at index {webcam_idx}")

d = sd.query_devices(webcam_idx)
print(f"Device name: {d['name']}")
print(f"Default sample rate: {d['default_samplerate']}")
print(f"Max input channels: {d['max_input_channels']}")

# Try recording 1 second at native rate
rate = int(d['default_samplerate'])
chunks = []
try:
    with sd.RawInputStream(samplerate=rate, blocksize=rate//4, dtype='int16', channels=1, device=1) as s:
        for _ in range(4):  # 4 chunks = 1 second
            data, _ = s.read(rate//4)
            chunks.append(bytes(data))
    total = b''.join(chunks)
    arr = np.frombuffer(total, dtype=np.int16)
    print(f"Recorded {len(arr)} samples at {rate}Hz")
    print(f"Audio level (max): {np.abs(arr).max()}")
    print("MIC_OK")
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)
