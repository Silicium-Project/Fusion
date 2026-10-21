#!/bin/bash
set -u

wallet_path="${SILICIUM_SOLANA_WALLET_PATH:-/data/solana-wallet.json}"
wallet_address="$(/usr/local/bin/solana-worker-wallet ensure "$wallet_path")" || exit 1
printf ' Devnet worker wallet: %s\n' "$wallet_address"

/usr/local/bin/compute_daemon &
compute_pid=$!

/usr/local/bin/p2p_node &
node_pid=$!

stop_children() {
  kill "$node_pid" "$compute_pid" 2>/dev/null || true
  wait "$node_pid" 2>/dev/null || true
  wait "$compute_pid" 2>/dev/null || true
}
trap stop_children INT TERM HUP

# Restart the whole container if either half of the worker fails. This keeps
# Docker's restart policy responsible for recovery without hiding a dead
# compute daemon behind a healthy P2P process.
wait -n "$node_pid" "$compute_pid" || true

stop_children
exit 1
