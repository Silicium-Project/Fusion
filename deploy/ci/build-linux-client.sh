#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"

cd "$ROOT"

if [[ ! -d "apps/silicium-node" || ! -d "Network/networked/p2p_node" ]]; then
  echo "Expected apps/silicium-node and Network/networked/p2p_node at $ROOT." >&2
  exit 1
fi

pushd apps/silicium-node >/dev/null
export SILICIUM_RELEASE_VERSION="${SILICIUM_RELEASE_VERSION:-$(node -p "require('./package.json').version")}"
export SILICIUM_RELEASE_CHANNEL="${SILICIUM_RELEASE_CHANNEL:-dev}"
export SILICIUM_RELEASE_BUILD="${SILICIUM_RELEASE_BUILD:-local}"

npm ci
npm run build
npm run prepare:runtime:linux

echo "Building p2p_node and compute_daemon..."
cargo build --release --manifest-path ../../Network/networked/p2p_node/Cargo.toml
cargo build --release --manifest-path ../../Network/networked/compute_daemon/Cargo.toml

mkdir -p src-tauri/resources/runtime/bin
cp ../../Network/networked/p2p_node/target/release/p2p_node src-tauri/resources/runtime/bin/
cp ../../Network/networked/compute_daemon/target/release/compute_daemon src-tauri/resources/runtime/bin/

cargo test --manifest-path src-tauri/Cargo.toml
npx tauri build --bundles deb
popd >/dev/null
