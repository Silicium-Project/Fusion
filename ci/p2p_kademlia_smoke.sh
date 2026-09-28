#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo ">> Running P2P Kademlia smoke test"
cargo test \
  --locked \
  --manifest-path "$ROOT/crates/p2p-node/Cargo.toml" \
  two_local_nodes_can_exchange_kademlia_records \
  -- --nocapture
