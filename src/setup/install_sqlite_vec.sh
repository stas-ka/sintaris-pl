#!/bin/bash
# =============================================================================
# install_sqlite_vec.sh — Install sqlite-vec SQLite vector search extension
# =============================================================================
# Installs the sqlite-vec Python package (pip3) which bundles a precompiled
# SQLite extension for ARM/aarch64/x86_64.
#
# Run standalone:   sudo bash src/setup/install_sqlite_vec.sh
# Called by:        install.sh Step 2 (included in the pip3 package list)
#
# After install, the store_sqlite.py module loads the extension automatically
# at startup via:   sqlite_vec.load(conn)
# =============================================================================

set -euo pipefail

echo "=============================================="
echo " sqlite-vec — SQLite vector search extension"
echo "=============================================="

# ---------------------------------------------------------------------------
# Install / upgrade the sqlite-vec Python package
# ---------------------------------------------------------------------------
echo "[1/2] Installing sqlite-vec Python package..."
pip3 install --break-system-packages --upgrade --quiet sqlite-vec
echo "  sqlite-vec installed."

# ---------------------------------------------------------------------------
# Verify the extension loads correctly
# ---------------------------------------------------------------------------
echo ""
echo "[2/2] Verifying sqlite-vec loads in Python..."
python3 - <<'PYEOF'
import sys
try:
    import sqlite3
    import sqlite_vec
    conn = sqlite3.connect(":memory:")
    sqlite_vec.load(conn)
    version_row = conn.execute("SELECT sqlite_vec_version()").fetchone()
    print(f"  OK — sqlite_vec version: {version_row[0]}")
    conn.close()
except ImportError:
    print("  ERROR: sqlite_vec module not found after install", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"  ERROR: failed to load extension: {e}", file=sys.stderr)
    sys.exit(1)
PYEOF

echo ""
echo "=============================================="
echo " sqlite-vec installed successfully."
echo " Vector search will be enabled automatically"
echo " by store_sqlite.py on next bot startup."
echo "=============================================="
