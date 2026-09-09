#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"

cd "$ROOT"

if [[ ! -d "apps/silicium-node" || ! -d "Network/networked/p2p_node" ]]; then
  echo "Expected apps/silicium-node and Network/networked/p2p_node at $ROOT." >&2
  exit 1
fi

# Use the runner capacity by default.  CI callers can still lower this when
# they deliberately need to share a constrained host.
export CARGO_BUILD_JOBS="${CARGO_BUILD_JOBS:-$(nproc)}"
export CARGO_INCREMENTAL="${CARGO_INCREMENTAL:-0}"

# Prime the exact AppImage tool cache before spending time compiling Rust.
bash "$ROOT/deploy/ci/prepare-tauri-linux-tools.sh"

pushd apps/silicium-node >/dev/null
export SILICIUM_RELEASE_VERSION="${SILICIUM_RELEASE_VERSION:-$(node -p "require('./package.json').version")}"
export SILICIUM_RELEASE_CHANNEL="${SILICIUM_RELEASE_CHANNEL:-dev}"
export SILICIUM_RELEASE_BUILD="${SILICIUM_RELEASE_BUILD:-local}"

npm ci
npm run build
npm run prepare:runtime:linux

# Avoid carrying a stale debug profile into the release build.  The
# release profile is reused by the tests and by the Tauri bundle below.
rm -rf -- \
  src-tauri/target/debug \
  ../../Network/networked/p2p_node/target/debug \
  ../../Network/networked/compute_daemon/target/debug \
  ../../Network/workloads/raytracer/native/target/debug

echo "Testing silicium-node in release mode..."
cargo test --release --locked --jobs "$CARGO_BUILD_JOBS" --manifest-path src-tauri/Cargo.toml
rm -rf -- src-tauri/target/debug

echo "Building p2p_node and compute_daemon..."
cargo build --release --locked --jobs "$CARGO_BUILD_JOBS" --manifest-path ../../Network/networked/p2p_node/Cargo.toml
cargo build --release --jobs "$CARGO_BUILD_JOBS" --manifest-path ../../Network/networked/compute_daemon/Cargo.toml

mkdir -p src-tauri/resources/runtime/bin
cp ../../Network/networked/p2p_node/target/release/p2p_node src-tauri/resources/runtime/bin/
cp ../../Network/networked/compute_daemon/target/release/compute_daemon src-tauri/resources/runtime/bin/

# Keep the runtime targets available to the next build.  They are ignored by
# git and are now covered by the Rust cache in both Linux workflows.  Set the
# escape hatch only on a host that is actually running out of disk space.
if [[ "${SILICIUM_RECLAIM_RUNTIME_TARGETS:-0}" == "1" ]]; then
  rm -rf -- \
    ../../Network/networked/p2p_node/target \
    ../../Network/networked/compute_daemon/target
fi

# The frontend was already built above; avoid invoking Vite a second time from
# Tauri's beforeBuildCommand.
export SILICIUM_SKIP_FRONTEND_BUILD="1"
npx tauri build --bundles deb,appimage
popd >/dev/null
