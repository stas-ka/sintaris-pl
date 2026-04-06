#!/usr/bin/env bash
# =============================================================================
# update_picoclaw.sh — PicoClaw (Pi) deploy wrapper (delegates to taris_deploy.sh)
# =============================================================================
# Retained for backward compatibility.
# Translates legacy options to taris_deploy.sh parameters.
#
# Usage (legacy):
#   bash src/setup/update_picoclaw.sh [--target pi2|pi1] [--yes] [--no-backup]
#                                      [--no-tests] [--force-restart]
#                                      [--upgrade-picoclaw → --upgrade-binary]
# =============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Translate legacy --upgrade-picoclaw to --upgrade-binary
args=()
for a in "$@"; do
  [[ "$a" == "--upgrade-picoclaw" ]] && args+=("--upgrade-binary") || args+=("$a")
done
exec bash "${SCRIPT_DIR}/taris_deploy.sh" --action deploy --variant picoclaw "${args[@]}"
