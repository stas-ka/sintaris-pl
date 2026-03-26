#!/usr/bin/env bash
# install_embedding_model.sh — Pre-download the default embedding model.
#
# Downloads "sentence-transformers/all-MiniLM-L6-v2" (~90 MB) using whichever
# backend is installed: fastembed (preferred) or sentence-transformers.
#
# Usage:
#   bash src/setup/install_embedding_model.sh [model_name]
#
# Optional env var:
#   EMBED_MODEL — override the model to pre-download
#                 (default: sentence-transformers/all-MiniLM-L6-v2)

set -e

MODEL="${EMBED_MODEL:-sentence-transformers/all-MiniLM-L6-v2}"
if [ -n "$1" ]; then
    MODEL="$1"
fi

echo "==> Embedding model: $MODEL"

# Try fastembed first (ARM-safe, ONNX Runtime)
if python3 -c "import fastembed" 2>/dev/null; then
    echo "==> Using fastembed to download model..."
    python3 - <<PYEOF
from fastembed import TextEmbedding
import sys
model_name = sys.argv[1] if len(sys.argv) > 1 else "$MODEL"
print(f"Downloading {model_name} via fastembed...")
svc = TextEmbedding(model_name=model_name)
# Warm-up: encode a short string to confirm model works
result = list(svc.embed(["test"]))
print(f"OK — dimension: {len(result[0])}")
PYEOF
    echo "==> fastembed model downloaded successfully."
    exit 0
fi

# Fall back to sentence-transformers (PyTorch)
if python3 -c "import sentence_transformers" 2>/dev/null; then
    echo "==> Using sentence-transformers to download model..."
    python3 - <<PYEOF
from sentence_transformers import SentenceTransformer
import numpy as np
model_name = "$MODEL"
print(f"Downloading {model_name} via sentence-transformers...")
svc = SentenceTransformer(model_name)
result = svc.encode(["test"])
print(f"OK — dimension: {result.shape[1]}")
PYEOF
    echo "==> sentence-transformers model downloaded successfully."
    exit 0
fi

echo ""
echo "ERROR: Neither fastembed nor sentence-transformers is installed."
echo "Install one of:"
echo "  pip install fastembed                 # recommended (ARM-safe)"
echo "  pip install sentence-transformers     # x86_64 with PyTorch"
exit 1
