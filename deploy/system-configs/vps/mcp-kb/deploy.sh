#!/usr/bin/env bash
# deploy.sh — Set up the taris_kb database on VPS-Supertaris
#
# ARCHITECTURE (v0.3): The MCP server is N8N's built-in MCP Server Trigger.
# No Docker container. No FastAPI. This script only:
#   1. Creates the taris_kb PostgreSQL database (if not exists)
#   2. Runs init_taris_kb.sql (idempotent schema creation)
#   3. Verifies the connection
#
# N8N workflows (MCP Server + ingest) are imported via the N8N UI or N8N API —
# NOT by this script. See doc/todo/4.3-remote-mcp-rag.md §9 Phase 2.
#
# Usage:
#   source .env
#   bash deploy/system-configs/vps/mcp-kb/deploy.sh
#
# Each VPS step requires SEPARATE explicit confirmation (VPS safety rule).

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../../" && pwd)"
DEPLOY_DIR="$PROJECT_ROOT/deploy/system-configs/vps/mcp-kb"

# ── Load secrets ──────────────────────────────────────────────────────────────
if [[ -f "$PROJECT_ROOT/.env" ]]; then
  set -a; source "$PROJECT_ROOT/.env"; set +a
fi

: "${VPS_HOST:?VPS_HOST not set in .env}"
: "${VPS_USER:?VPS_USER not set in .env}"
: "${VPS_PWD:?VPS_PWD not set in .env}"

SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=10"
SCP_OPTS="-o StrictHostKeyChecking=no"
REMOTE="${VPS_USER}@${VPS_HOST}"

_ssh() { sshpass -p "$VPS_PWD" ssh $SSH_OPTS "$REMOTE" "$@"; }

YES=0
for arg in "$@"; do [[ "$arg" == "--yes" ]] && YES=1; done

confirm() {
  [[ $YES -eq 1 ]] && return 0
  echo ""
  echo "⚠️  VPS-Supertaris operation: $1"
  read -rp "Proceed? (yes/no): " ans
  [[ "$ans" == "yes" ]] || { echo "Skipped."; return 1; }
}

echo "=== taris_kb DB setup on $VPS_HOST ==="

# ── Step 1: create taris_kb database ─────────────────────────────────────────
confirm "Create PostgreSQL database 'taris_kb' and run init_taris_kb.sql" || { echo "DB setup skipped."; exit 0; }

# Copy SQL to VPS
sshpass -p "$VPS_PWD" scp $SCP_OPTS "$DEPLOY_DIR/init_taris_kb.sql" "$REMOTE:/tmp/init_taris_kb.sql"

# Create DB (ignore error if already exists), then run schema
_ssh "sudo -u postgres psql -c \"CREATE DATABASE taris_kb;\" 2>/dev/null || true"
_ssh "sudo -u postgres psql -d taris_kb -f /tmp/init_taris_kb.sql"
_ssh "rm -f /tmp/init_taris_kb.sql"
echo "✓ taris_kb schema applied"

# ── Step 2: verify ────────────────────────────────────────────────────────────
_ssh "sudo -u postgres psql -d taris_kb -c '\\dt'" | grep kb_chunks && echo "✓ kb_chunks table exists" || echo "⚠ kb_chunks not found — check SQL output above"

echo ""
echo "✅ taris_kb DB ready"
echo ""
echo "Next steps (all require separate confirmation):"
echo "  1. Import N8N workflows via N8N UI or N8N API:"
echo "     - KB MCP Server workflow (MCP Server Trigger node)"
echo "     - KB Ingest workflow (Webhook Trigger + Docling + pgvector)"
echo "  2. Add N8N_KB_API_KEY and N8N_KB_TOKEN to bot.env on all Taris targets"
echo "  3. Set MCP_REMOTE_URL to N8N MCP Server SSE endpoint in bot.env"
echo "  4. Set REMOTE_KB_ENABLED=1 after N8N workflows are tested"

