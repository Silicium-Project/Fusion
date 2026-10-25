#!/usr/bin/env bash
# Prepares the Linux runtime bundled in the AppImage/deb/rpm
# (src-tauri/resources/runtime): the Rust node (p2p_node), the compute daemon
# (compute_daemon) and the native raytracer, plus the raytracer environment
# file read by the app. The network runtime needs no Python.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$APP_ROOT/../.." && pwd)"
NETWORK_ROOT="$REPO_ROOT/network"
RUNTIME_ROOT="$APP_ROOT/src-tauri/resources/runtime"
RUNTIME_NETWORK="$RUNTIME_ROOT/Network"
NATIVE_RAYTRACER_MANIFEST="$NETWORK_ROOT/crates/raytracer/Cargo.toml"
NATIVE_RAYTRACER_TARGET="$APP_ROOT/src-tauri/target/raytracer-native"

[[ -f "$NATIVE_RAYTRACER_MANIFEST" ]] || { echo "Native raytracer manifest not found: $NATIVE_RAYTRACER_MANIFEST" >&2; exit 1; }
[[ "$RUNTIME_ROOT" == "$APP_ROOT"/* ]] || { echo "Unsafe runtime target: $RUNTIME_ROOT" >&2; exit 1; }

CARGO_TARGET_DIR="$NATIVE_RAYTRACER_TARGET" cargo build --release --manifest-path "$NATIVE_RAYTRACER_MANIFEST"
if [[ ! -x "$NETWORK_ROOT/target/release/p2p_node" || ! -x "$NETWORK_ROOT/target/release/compute_daemon" ]]; then
  cargo build --release --locked --manifest-path "$NETWORK_ROOT/Cargo.toml" -p p2p_node -p compute_daemon
fi

rm -rf -- "$RUNTIME_ROOT"
install -d "$RUNTIME_NETWORK/bin/raytracer" "$RUNTIME_ROOT/.silicium/env"
install -m 0755 "$NETWORK_ROOT/target/release/p2p_node" "$RUNTIME_NETWORK/bin/p2p_node"
install -m 0755 "$NETWORK_ROOT/target/release/compute_daemon" "$RUNTIME_NETWORK/bin/compute_daemon"
install -m 0755 "$NATIVE_RAYTRACER_TARGET/release/silicium-raytracer" "$RUNTIME_NETWORK/bin/raytracer/silicium-raytracer"

cat > "$RUNTIME_ROOT/.silicium/env/raytracer.env" <<'EOF'
SILICIUM_RAYTRACER_BIN=Network/bin/raytracer/silicium-raytracer
SILICIUM_RAYTRACER_ASSETS_DIR=Network/bin/raytracer
EOF

echo "Linux runtime prepared: $RUNTIME_ROOT"
