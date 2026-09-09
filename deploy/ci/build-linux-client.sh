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
cargo test --release --jobs "$CARGO_BUILD_JOBS" --manifest-path src-tauri/Cargo.toml
rm -rf -- src-tauri/target/debug

echo "Building p2p_node and compute_daemon..."
cargo build --release --jobs "$CARGO_BUILD_JOBS" --manifest-path ../../Network/networked/p2p_node/Cargo.toml
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

# Tauri downloads this script lazily while producing the AppImage. Prime the
# same cache with retries so a transient raw.githubusercontent.com timeout does
# not discard the already completed Rust and frontend build.
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"
tauri_tools_dir="$XDG_CACHE_HOME/tauri"
gtk_plugin="$tauri_tools_dir/linuxdeploy-plugin-gtk.sh"
mkdir -p "$tauri_tools_dir"
if [[ ! -s "$gtk_plugin" ]]; then
  gtk_plugin_tmp="${gtk_plugin}.download.$$"
  trap 'rm -f -- "$gtk_plugin_tmp"' EXIT
  curl --fail --show-error --location \
    --connect-timeout 20 --max-time 300 \
    --retry 10 --retry-all-errors --retry-delay 5 --retry-max-time 900 \
    --output "$gtk_plugin_tmp" \
    "https://raw.githubusercontent.com/tauri-apps/linuxdeploy-plugin-gtk/master/linuxdeploy-plugin-gtk.sh"
  chmod +x "$gtk_plugin_tmp"
  mv -f -- "$gtk_plugin_tmp" "$gtk_plugin"
  trap - EXIT
fi
chmod +x "$gtk_plugin"
npx tauri build --bundles deb,appimage
popd >/dev/null
