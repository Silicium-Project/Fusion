#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$APP_ROOT/../.." && pwd)"
NETWORK_ROOT="$REPO_ROOT/Network"
RUNTIME_ROOT="$APP_ROOT/src-tauri/resources/runtime"
RUNTIME_NETWORK="$RUNTIME_ROOT/Network"
NATIVE_RAYTRACER_MANIFEST="$NETWORK_ROOT/workloads/raytracer/native/Cargo.toml"
NATIVE_RAYTRACER_TARGET="$APP_ROOT/src-tauri/target/raytracer-native"

[[ -f "$NETWORK_ROOT/silicium" ]] || { echo "Network runtime not found: $NETWORK_ROOT" >&2; exit 1; }
[[ -f "$NATIVE_RAYTRACER_MANIFEST" ]] || { echo "Native raytracer manifest not found: $NATIVE_RAYTRACER_MANIFEST" >&2; exit 1; }
[[ "$RUNTIME_ROOT" == "$APP_ROOT"/* ]] || { echo "Unsafe runtime target: $RUNTIME_ROOT" >&2; exit 1; }

CARGO_TARGET_DIR="$NATIVE_RAYTRACER_TARGET" cargo build --release --manifest-path "$NATIVE_RAYTRACER_MANIFEST"
rm -rf -- "$RUNTIME_ROOT"
install -d "$RUNTIME_NETWORK" "$RUNTIME_ROOT/.silicium/env" "$RUNTIME_ROOT/tools/python/site-packages"
install -d "$RUNTIME_ROOT/deploy/linux"
install -m 0755 "$NETWORK_ROOT/silicium" "$RUNTIME_NETWORK/silicium"
install -m 0755 "$REPO_ROOT/deploy/linux/start-node.sh" "$RUNTIME_ROOT/deploy/linux/start-node.sh"
cp -a "$NETWORK_ROOT/tools" "$RUNTIME_NETWORK/tools"
for optional in workloads bin; do
  if [[ -d "$NETWORK_ROOT/$optional" ]]; then
    cp -a "$NETWORK_ROOT/$optional" "$RUNTIME_NETWORK/$optional"
  fi
done
rm -rf -- "$RUNTIME_NETWORK/workloads/raytracer/native/target"
install -d "$RUNTIME_NETWORK/bin/raytracer"
install -m 0755 "$NATIVE_RAYTRACER_TARGET/release/silicium-raytracer" "$RUNTIME_NETWORK/bin/raytracer/silicium-raytracer"
if [[ -d "$NETWORK_ROOT/networked" ]]; then
  networked_source="$NETWORK_ROOT/networked"
elif [[ -d "$NETWORK_ROOT/demo/networked" ]]; then
  networked_source="$NETWORK_ROOT/demo/networked"
else
  networked_source=""
fi
if [[ -n "$networked_source" ]]; then
  install -d "$RUNTIME_NETWORK/networked"
  install -m 0644 \
    "$networked_source/__init__.py" \
    "$networked_source/networked_runtime.py" \
    "$RUNTIME_NETWORK/networked/"
fi

cat > "$RUNTIME_ROOT/.silicium/env/raytracer.env" <<'EOF'
SILICIUM_RAYTRACER_BIN=Network/bin/raytracer/silicium-raytracer
SILICIUM_RAYTRACER_ASSETS_DIR=Network/bin/raytracer
EOF

if [[ -f "$NETWORK_ROOT/requirements-p2p.txt" ]]; then
  python3 -m pip install \
    --disable-pip-version-check \
    --no-compile \
    --target "$RUNTIME_ROOT/tools/python/site-packages" \
    -r "$NETWORK_ROOT/requirements-p2p.txt"
fi

find "$RUNTIME_ROOT" -type d -name __pycache__ -prune -exec rm -rf -- {} +
find "$RUNTIME_ROOT" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import aioice, cryptography' "$RUNTIME_ROOT/tools/python/site-packages"
echo "Linux runtime prepared: $RUNTIME_ROOT"
