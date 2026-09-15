#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"

cd "$ROOT"

# A stale release target can consume the remaining VPS disk before Tauri gets
# to the AppImage step. Reclaim build-only targets only when the host is below
# the safety threshold; otherwise keep them for incremental builds.
minimum_free_kb="${SILICIUM_MIN_FREE_KB:-16777216}"
reclaim_runtime_targets="${SILICIUM_RECLAIM_RUNTIME_TARGETS:-auto}"
free_kb="$(df -Pk "$ROOT" | awk 'NR == 2 {print $4}')"
if [[ -n "$free_kb" && "$free_kb" -lt "$minimum_free_kb" ]]; then
  echo "Low disk space (${free_kb} KiB free); reclaiming stale Rust build targets."
  rm -rf -- \
    apps/silicium-node/src-tauri/target \
    Network/networked/p2p_node/target \
    Network/networked/compute_daemon/target \
    Network/workloads/raytracer/native/target
fi

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
export SILICIUM_RELEASE_CHANNEL="${SILICIUM_RELEASE_CHANNEL:-dev}"
export SILICIUM_RELEASE_BUILD="${SILICIUM_RELEASE_BUILD:-local}"

if [[ -z "${SILICIUM_RELEASE_VERSION:-}" ]]; then
  if [[ "$SILICIUM_RELEASE_CHANNEL" == "prod" ]]; then
    export SILICIUM_RELEASE_VERSION="$(node -p "require('./src-tauri/tauri.prod.conf.json').version")"
  else
    export SILICIUM_RELEASE_VERSION="$(node -p "require('./package.json').version")"
  fi
fi
if [[ -z "${SILICIUM_UPDATE_MANIFEST_URL:-}" ]]; then
  if [[ "$SILICIUM_RELEASE_CHANNEL" == "prod" ]]; then
    export SILICIUM_UPDATE_MANIFEST_URL="https://vps-910c1dbc.vps.ovh.net/downloads/update-manifest.json"
  else
    export SILICIUM_UPDATE_MANIFEST_URL="https://10.77.0.1:8443/downloads/update-manifest.json"
  fi
fi

tauri_config_args=()
if [[ "$SILICIUM_RELEASE_CHANNEL" == "prod" ]]; then
  tauri_config_args+=(--config src-tauri/tauri.prod.conf.json)
fi

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

if [[ "${SILICIUM_RUN_RELEASE_TESTS:-0}" == "1" ]]; then
  echo "Testing silicium-node in release mode..."
  cargo test --release --locked --jobs "$CARGO_BUILD_JOBS" --manifest-path src-tauri/Cargo.toml
else
  echo "Skipping duplicate release tests; the node-fast lane owns this validation."
fi
rm -rf -- src-tauri/target/debug

echo "Building p2p_node and compute_daemon..."
cargo build --release --locked --jobs "$CARGO_BUILD_JOBS" --manifest-path ../../Network/networked/p2p_node/Cargo.toml
cargo build --release --jobs "$CARGO_BUILD_JOBS" --manifest-path ../../Network/networked/compute_daemon/Cargo.toml

mkdir -p src-tauri/resources/runtime/bin
cp ../../Network/networked/p2p_node/target/release/p2p_node src-tauri/resources/runtime/bin/
cp ../../Network/networked/compute_daemon/target/release/compute_daemon src-tauri/resources/runtime/bin/

# Keep the runtime targets available to the next build when disk allows it.
# The CI lanes use `auto`: after copying the runtime binaries, reclaim the
# compiler-only targets if the host is close to full. `1` remains an explicit
# override for a constrained runner.
runtime_free_kb="$(df -Pk "$ROOT" | awk 'NR == 2 {print $4}')"
if [[ "$reclaim_runtime_targets" == "1" ]] || \
   [[ "$reclaim_runtime_targets" == "auto" && -n "$runtime_free_kb" && "$runtime_free_kb" -lt "$minimum_free_kb" ]]; then
  rm -rf -- \
    src-tauri/target/raytracer-native \
    ../../Network/networked/p2p_node/target \
    ../../Network/networked/compute_daemon/target
fi

df -h "$ROOT"

# The frontend was already built above; avoid invoking Vite a second time from
# Tauri's beforeBuildCommand.
export SILICIUM_SKIP_FRONTEND_BUILD="1"
npx tauri build --bundles deb,appimage,rpm "${tauri_config_args[@]}"

appimage_path="$(find src-tauri/target/release/bundle/appimage -maxdepth 1 -type f -name '*.AppImage' -print -quit)"
deb_path="$(find src-tauri/target/release/bundle/deb -maxdepth 1 -type f -name '*.deb' -print -quit)"
rpm_path="$(find src-tauri/target/release/bundle/rpm -maxdepth 1 -type f -name '*.rpm' -print -quit)"
bash "$ROOT/deploy/ci/verify-linux-bundles.sh" "$appimage_path" "$deb_path" "$rpm_path"
popd >/dev/null
