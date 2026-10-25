#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo ">> Running P2P Kademlia smoke test"
rustup_bin="$(command -v rustup || true)"
if [[ -z "$rustup_bin" && -x "${CARGO_HOME:-$HOME/.cargo}/bin/rustup" ]]; then
  rustup_bin="${CARGO_HOME:-$HOME/.cargo}/bin/rustup"
fi
if [[ -z "$rustup_bin" ]]; then
  echo "rustup is missing from PATH and CARGO_HOME." >&2
  exit 127
fi

"$rustup_bin" run "${RUSTUP_TOOLCHAIN:-stable}" cargo test \
  --locked \
  --manifest-path "$ROOT/crates/p2p-node/Cargo.toml" \
  two_local_nodes_can_exchange_kademlia_records \
  -- --nocapture
