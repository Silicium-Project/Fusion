#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export ANCHOR_WALLET="${ANCHOR_WALLET:-$HOME/.config/solana/id.json}"
export ANCHOR_PROVIDER_URL="${ANCHOR_PROVIDER_URL:-http://127.0.0.1:8899}"

if [ ! -f "$ANCHOR_WALLET" ]; then
  echo "Wallet not found at $ANCHOR_WALLET. Creating one..."
  solana-keygen new --outfile "$ANCHOR_WALLET" --no-bip39-passphrase
fi

LOG_DIR="${SILICIUM_LOG_DIR:-/tmp}"
mkdir -p "$LOG_DIR"

TIMESTAMP="$(date +"%Y%m%d-%H%M%S")"
VALIDATOR_LOG="${VALIDATOR_LOG:-$LOG_DIR/silicium-solana-test-validator-$TIMESTAMP.log}"
VALIDATOR_PID=""

cleanup() {
  if [ -n "$VALIDATOR_PID" ] && ps -p "$VALIDATOR_PID" >/dev/null 2>&1; then
    echo "Stopping solana-test-validator..."
    kill "$VALIDATOR_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

if pgrep -f "solana-test-validator" >/dev/null 2>&1; then
  echo "Stopping existing solana-test-validator..."
  pkill -f "solana-test-validator" || true
  sleep 2
fi

echo "Starting solana-test-validator --reset..."
solana-test-validator --reset > "$VALIDATOR_LOG" 2>&1 &
VALIDATOR_PID=$!

sleep 5

solana config set --url localhost >/dev/null

echo "Airdropping SOL to local wallet..."
solana airdrop 20 >/dev/null || true

echo "Syncing Anchor keys..."
anchor keys sync --provider.cluster localnet

echo "Building Anchor program..."
anchor build

echo "Deploying Anchor program..."
if command -v anchor >/dev/null 2>&1; then
  anchor program deploy target/deploy/solana_layer.so --provider.cluster localnet
else
  echo "Anchor command not found. Install Anchor first."
  exit 1
fi

echo "Installing SDK dependencies if needed..."
if [ -f "../sdk/package.json" ]; then
  (cd ../sdk && npm ci)
fi

echo "Running full SDK flow..."
(cd ../sdk && npx ts-node examples/full-flow.ts)

echo "Done. Validator log: $VALIDATOR_LOG"
