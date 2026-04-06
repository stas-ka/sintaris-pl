#!/usr/bin/env bash
# =============================================================================
# update_openclaw.sh — OpenClaw deploy wrapper (delegates to taris_deploy.sh)
# =============================================================================
# Retained for backward compatibility.
# Translates legacy options to taris_deploy.sh parameters.
#
# Usage (legacy):
#   bash src/setup/update_openclaw.sh [--target ts2|ts1] [--yes] [--no-backup]
#                                      [--no-tests] [--force-restart]
# =============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${SCRIPT_DIR}/taris_deploy.sh" --action deploy --variant openclaw "$@"
