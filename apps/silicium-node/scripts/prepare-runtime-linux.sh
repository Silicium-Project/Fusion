#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$APP_ROOT/../.." && pwd)"
NETWORK_ROOT="$REPO_ROOT/Network"
RUNTIME_ROOT="$APP_ROOT/src-tauri/resources/runtime"
RUNTIME_NETWORK="$RUNTIME_ROOT/Network"

[[ -f "$NETWORK_ROOT/silicium" ]] || { echo "Network runtime not found: $NETWORK_ROOT" >&2; exit 1; }
[[ "$RUNTIME_ROOT" == "$APP_ROOT"/* ]] || { echo "Unsafe runtime target: $RUNTIME_ROOT" >&2; exit 1; }

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
if [[ -d "$NETWORK_ROOT/networked" ]]; then
  cp -a "$NETWORK_ROOT/networked" "$RUNTIME_NETWORK/networked"
elif [[ -d "$NETWORK_ROOT/demo/networked" ]]; then
  cp -a "$NETWORK_ROOT/demo/networked" "$RUNTIME_NETWORK/networked"
fi

cat > "$RUNTIME_ROOT/.silicium/env/raytracer.env" <<'EOF'
SILICIUM_RAYTRACER_BIN=Network/bin/raytracer/raytracer.py
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
