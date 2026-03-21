#!/bin/bash
# =============================================================================
# backup_image.sh — Full SD Card System Image Backup  (§6.3.1)
# =============================================================================
# Creates a compressed, checksummed full-disk image of the Pi SD card.
#
# Usage:
#   sudo bash backup_image.sh [--device /dev/mmcblk0] [--dest /mnt/ssd/backups/images]
#
# Requirements (installed by this script if missing):
#   apt: zstd
#
# Output:
#   <dest>/mico-image-rpi3-YYYY-MM-DD.img.zst
#   <dest>/mico-image-rpi3-YYYY-MM-DD.img.zst.sha256
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults (override via flags)
# ---------------------------------------------------------------------------
DEVICE="/dev/mmcblk0"          # SD card; adjust if booting from SSD
DEST_DIR="/mnt/ssd/backups/images"
HOSTNAME_LABEL="rpi3"
DATE="$(date +%Y-%m-%d)"
ARCHIVE_NAME="mico-image-${HOSTNAME_LABEL}-${DATE}.img.zst"

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --device) DEVICE="$2";    shift 2 ;;
    --dest)   DEST_DIR="$2";  shift 2 ;;
    *) echo "[!] Unknown argument: $1"; exit 1 ;;
  esac
done

ARCHIVE_PATH="${DEST_DIR}/${ARCHIVE_NAME}"
CHECKSUM_PATH="${ARCHIVE_PATH}.sha256"

# ---------------------------------------------------------------------------
echo "=============================================="
echo " Taris Bot — Full Image Backup"
echo "=============================================="
echo "  Source device : ${DEVICE}"
echo "  Destination   : ${ARCHIVE_PATH}"
echo ""

# Must be root
if [[ "$(id -u)" -ne 0 ]]; then
  echo "[!] Run as root: sudo bash $0"
  exit 1
fi

# Verify device exists
if [[ ! -b "${DEVICE}" ]]; then
  echo "[!] Block device not found: ${DEVICE}"
  echo "    Available devices:"
  lsblk -d -o NAME,SIZE,MODEL 2>/dev/null || ls /dev/mmcblk* /dev/sd* 2>/dev/null
  exit 1
fi

# Create destination directory
mkdir -p "${DEST_DIR}"

# Ensure zstd is available
if ! command -v zstd &>/dev/null; then
  echo "[i] Installing zstd..."
  apt-get install -y zstd
fi

# ---------------------------------------------------------------------------
# Estimate size
# ---------------------------------------------------------------------------
DEVICE_BYTES=$(blockdev --getsize64 "${DEVICE}" 2>/dev/null || echo 0)
DEVICE_GB=$(( DEVICE_BYTES / 1024 / 1024 / 1024 ))
echo "[i] Device size: ~${DEVICE_GB} GB"
echo "[i] Starting image capture + compression (may take 10-30 min)..."
echo ""

START_TIME=$(date +%s)

# ---------------------------------------------------------------------------
# Create image: dd | zstd
# ---------------------------------------------------------------------------
dd if="${DEVICE}" bs=4M status=progress 2>&1 | \
  zstd -T0 -5 -o "${ARCHIVE_PATH}"

END_TIME=$(date +%s)
ELAPSED=$(( END_TIME - START_TIME ))
ARCHIVE_MB=$(( $(stat -c%s "${ARCHIVE_PATH}") / 1024 / 1024 ))

echo ""
echo "[✓] Image created: ${ARCHIVE_PATH}"
echo "    Size     : ${ARCHIVE_MB} MB"
echo "    Duration : ${ELAPSED}s"

# ---------------------------------------------------------------------------
# Checksum
# ---------------------------------------------------------------------------
echo "[i] Generating SHA-256 checksum..."
sha256sum "${ARCHIVE_PATH}" > "${CHECKSUM_PATH}"
echo "[✓] Checksum saved: ${CHECKSUM_PATH}"
cat "${CHECKSUM_PATH}"

# ---------------------------------------------------------------------------
# List backups in dest dir
# ---------------------------------------------------------------------------
echo ""
echo "[i] Backups in ${DEST_DIR}:"
ls -lh "${DEST_DIR}/"*.img.zst 2>/dev/null || echo "  (none)"

echo ""
echo "=============================================="
echo " Backup complete."
echo "=============================================="
echo ""
echo "  Restore command:"
echo "    zstd -d ${ARCHIVE_PATH} --stdout | sudo dd of=/dev/sdX bs=4M status=progress"
echo ""
echo "  Verify checksum after copy:"
echo "    sha256sum -c ${CHECKSUM_PATH}"
