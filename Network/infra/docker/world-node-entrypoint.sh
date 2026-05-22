#!/bin/sh
set -eu

SOLANA_LAYER_DIR="/workspace/solana-layer"

if [ -f "$SOLANA_LAYER_DIR/package.json" ] && [ ! -d "$SOLANA_LAYER_DIR/node_modules/@coral-xyz/anchor" ]; then
  echo "[world-node] Installing missing Solana JS dependencies into bind-mounted repo..."
  cd "$SOLANA_LAYER_DIR"
  npm install --include=dev --no-audit --no-fund
fi

exec python3 /workspace/silicium "$@"
