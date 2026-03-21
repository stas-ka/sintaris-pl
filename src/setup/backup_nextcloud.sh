#!/bin/bash
# =============================================================================
# backup_nextcloud.sh — Remote Backup to Nextcloud via WebDAV  (§6.3.3)
# =============================================================================
# Uploads image backups and recovery bundles to a Nextcloud instance.
# Also supports download and integrity verification.
#
# Usage:
#   bash backup_nextcloud.sh upload <file>        # upload a file
#   bash backup_nextcloud.sh download <filename>  # download to current dir
#   bash backup_nextcloud.sh list [images|recovery|logs]  # list remote files
#   bash backup_nextcloud.sh verify <file>        # verify local SHA-256
#   bash backup_nextcloud.sh prune images --keep 3  # delete oldest, keep N
#
# Configuration (set in environment or bot.env):
#   NEXTCLOUD_URL     https://cloud.example.com
#   NEXTCLOUD_USER    backup_user
#   NEXTCLOUD_PASS    app_password
#   NEXTCLOUD_REMOTE  /MicoBackups       (WebDAV path inside Nextcloud)
#
# Source secrets from ~/.taris/bot.env if set:
#   NEXTCLOUD_URL=...
#   NEXTCLOUD_USER=...
#   NEXTCLOUD_PASS=...
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Load configuration
# ---------------------------------------------------------------------------
BOT_ENV="${HOME}/.taris/bot.env"
[[ -f "${BOT_ENV}" ]] && source "${BOT_ENV}"

NEXTCLOUD_URL="${NEXTCLOUD_URL:-}"
NEXTCLOUD_USER="${NEXTCLOUD_USER:-}"
NEXTCLOUD_PASS="${NEXTCLOUD_PASS:-}"
NEXTCLOUD_REMOTE="${NEXTCLOUD_REMOTE:-/MicoBackups}"
WEBDAV_BASE="${NEXTCLOUD_URL}/remote.php/dav/files/${NEXTCLOUD_USER}${NEXTCLOUD_REMOTE}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
check_config() {
  local missing=()
  [[ -z "${NEXTCLOUD_URL}"   ]] && missing+=("NEXTCLOUD_URL")
  [[ -z "${NEXTCLOUD_USER}"  ]] && missing+=("NEXTCLOUD_USER")
  [[ -z "${NEXTCLOUD_PASS}"  ]] && missing+=("NEXTCLOUD_PASS")
  if [[ ${#missing[@]} -gt 0 ]]; then
    echo "[!] Missing config variables: ${missing[*]}"
    echo "    Set them in ~/.taris/bot.env or export before running."
    exit 1
  fi
}

webdav_curl() {
  curl --silent --show-error --fail \
       --user "${NEXTCLOUD_USER}:${NEXTCLOUD_PASS}" \
       "$@"
}

detect_category() {
  local fname="$1"
  if [[ "${fname}" == *.img.zst ]]; then
    echo "images"
  elif [[ "${fname}" == *bundle* || "${fname}" == *recovery* ]]; then
    echo "recovery"
  elif [[ "${fname}" == *.log* ]]; then
    echo "logs"
  else
    echo "recovery"
  fi
}

ensure_remote_dirs() {
  for dir in images recovery logs; do
    webdav_curl -X MKCOL "${WEBDAV_BASE}/${dir}/" 2>/dev/null || true
  done
}

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
cmd_upload() {
  local file="$1"
  check_config

  [[ ! -f "${file}" ]] && { echo "[!] File not found: ${file}"; exit 1; }

  local fname
  fname="$(basename "${file}")"
  local category
  category="$(detect_category "${fname}")"
  local dest="${WEBDAV_BASE}/${category}/${fname}"

  echo "[i] Uploading ${fname} to ${NEXTCLOUD_REMOTE}/${category}/ ..."
  ensure_remote_dirs

  # Upload with progress
  webdav_curl --upload-file "${file}" --progress-bar "${dest}"
  echo ""
  echo "[✓] Uploaded: ${dest}"

  # Upload checksum (if it exists alongside the file)
  local checksum_file="${file}.sha256"
  if [[ -f "${checksum_file}" ]]; then
    webdav_curl --upload-file "${checksum_file}" \
                "${dest}.sha256" --silent
    echo "[✓] Checksum uploaded: ${fname}.sha256"
  else
    # Generate and upload checksum on the fly
    echo "[i] Generating checksum..."
    sha256sum "${file}" > "/tmp/${fname}.sha256"
    webdav_curl --upload-file "/tmp/${fname}.sha256" \
                "${dest}.sha256" --silent
    echo "[✓] Checksum uploaded."
    cp "/tmp/${fname}.sha256" "$(dirname "${file}")/${fname}.sha256"
  fi
}

cmd_download() {
  local fname="$1"
  local dest_dir="${2:-$(pwd)}"
  check_config

  local category
  category="$(detect_category "${fname}")"
  local remote="${WEBDAV_BASE}/${category}/${fname}"
  local local_path="${dest_dir}/${fname}"

  echo "[i] Downloading ${fname} from ${NEXTCLOUD_REMOTE}/${category}/ ..."
  webdav_curl --output "${local_path}" --progress-bar "${remote}"
  echo ""

  # Try to download checksum file too
  webdav_curl --output "${local_path}.sha256" \
              "${remote}.sha256" --silent 2>/dev/null || true

  if [[ -f "${local_path}.sha256" ]]; then
    echo "[i] Verifying checksum..."
    (cd "${dest_dir}" && sha256sum -c "${fname}.sha256")
  fi

  echo "[✓] Downloaded: ${local_path}"
}

cmd_list() {
  local category="${1:-}"
  check_config

  if [[ -n "${category}" ]]; then
    echo "[i] Listing ${NEXTCLOUD_REMOTE}/${category}/:"
    webdav_curl -X PROPFIND \
                -H "Depth: 1" \
                "${WEBDAV_BASE}/${category}/" | \
      grep -oP '(?<=<d:href>)[^<]+' | \
      grep -v "/$" | \
      awk -F/ '{print $NF}' | \
      grep -v "^$" | sort || true
  else
    for dir in images recovery logs; do
      echo ""
      echo "=== ${NEXTCLOUD_REMOTE}/${dir}/ ==="
      webdav_curl -X PROPFIND \
                  -H "Depth: 1" \
                  "${WEBDAV_BASE}/${dir}/" 2>/dev/null | \
        grep -oP '(?<=<d:href>)[^<]+' | \
        grep -v "/$" | \
        awk -F/ '{print $NF}' | \
        grep -v "^$" | sort || echo "  (empty)"
    done
  fi
}

cmd_verify() {
  local file="$1"
  [[ ! -f "${file}" ]] && { echo "[!] File not found: ${file}"; exit 1; }

  local fname
  fname="$(basename "${file}")"
  local checksum_file
  checksum_file="$(dirname "${file}")/${fname}.sha256"

  if [[ ! -f "${checksum_file}" ]]; then
    echo "[!] Checksum file not found: ${checksum_file}"
    exit 1
  fi

  echo "[i] Verifying checksum for ${fname}..."
  (cd "$(dirname "${file}")" && sha256sum -c "${fname}.sha256")
  echo "[✓] Integrity OK."
}

cmd_prune() {
  local category="${1:-images}"
  local keep=3
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --keep) keep="$2"; shift 2 ;;
      *) shift ;;
    esac
  done
  check_config

  echo "[i] Pruning ${NEXTCLOUD_REMOTE}/${category}/ — keeping latest ${keep} files..."

  # List files sorted newest first, skip .sha256 sidecar files
  mapfile -t files < <(webdav_curl -X PROPFIND -H "Depth: 1" \
                         "${WEBDAV_BASE}/${category}/" 2>/dev/null | \
    grep -oP '(?<=<d:href>)[^<]+' | \
    grep -v "/$" | \
    awk -F/ '{print $NF}' | \
    grep -v "^$" | grep -v '\.sha256$' | sort -r || true)

  local total=${#files[@]}
  echo "[i] Found ${total} file(s) in ${category}/"

  if [[ ${total} -le ${keep} ]]; then
    echo "[i] Nothing to prune (${total} <= ${keep})."
    return
  fi

  local delete_count=$(( total - keep ))
  echo "[i] Will delete ${delete_count} oldest file(s)."

  local idx=0
  for fname in "${files[@]}"; do
    idx=$(( idx + 1 ))
    if [[ ${idx} -gt ${keep} ]]; then
      webdav_curl -X DELETE "${WEBDAV_BASE}/${category}/${fname}" --silent
      # Also delete checksum sidecar if present
      webdav_curl -X DELETE "${WEBDAV_BASE}/${category}/${fname}.sha256" \
                  --silent 2>/dev/null || true
      echo "  Deleted: ${fname}"
    fi
  done

  echo "[✓] Prune complete."
}

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
COMMAND="${1:-help}"
shift || true

case "${COMMAND}" in
  upload)   cmd_upload   "$@" ;;
  download) cmd_download "$@" ;;
  list)     cmd_list     "$@" ;;
  verify)   cmd_verify   "$@" ;;
  prune)    cmd_prune    "$@" ;;
  help|--help|-h)
    cat << 'HELP'
backup_nextcloud.sh — Nextcloud WebDAV backup tool

Commands:
  upload <local_file>              Upload file (auto-detects category)
  download <filename> [dest_dir]   Download file + verify checksum
  list [images|recovery|logs]      List remote files by category
  verify <local_file>              Verify local file against .sha256
  prune <category> [--keep N]      Delete oldest files, keep N newest

Category mapping:
  *.img.zst, *.img.gz  → images/
  *bundle*, *recovery* → recovery/
  *.log*               → logs/

Configuration (in ~/.taris/bot.env or environment):
  NEXTCLOUD_URL         https://cloud.example.com
  NEXTCLOUD_USER        username
  NEXTCLOUD_PASS        app_password
  NEXTCLOUD_REMOTE      /MicoBackups  (default)

Examples:
  bash backup_nextcloud.sh upload mico-image-rpi3-2026-03-07.img.zst
  bash backup_nextcloud.sh list images
  bash backup_nextcloud.sh download mico-image-rpi3-2026-03-07.img.zst
  bash backup_nextcloud.sh prune images --keep 3
HELP
    ;;
  *)
    echo "[!] Unknown command: ${COMMAND}"
    echo "    Run with 'help' for usage."
    exit 1
    ;;
esac
