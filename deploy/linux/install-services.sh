#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/opt/silicium}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/linux/install-services.sh $ROOT" >&2
  exit 1
fi

[[ -d "$ROOT/deploy/systemd" ]] || { echo "Missing deployment files under: $ROOT" >&2; exit 1; }
cd "$ROOT"

if ! python3 - <<'PY'
import importlib.util
import sys

missing = [
    name for name in ("zmq", "google.protobuf")
    if importlib.util.find_spec(name) is None
]
sys.exit(0 if not missing else 1)
PY
then
  apt-get update
  apt-get install -y --no-install-recommends python3-cryptography python3-protobuf python3-zmq
fi

if ! python3 -c 'import cryptography' >/dev/null 2>&1; then
  apt-get update
  apt-get install -y --no-install-recommends python3-cryptography
fi

mkdir -p /etc/silicium /var/lib/silicium/site /var/lib/silicium/network /var/lib/silicium/solana /var/lib/silicium/downloads

ORCHESTRATOR_ENV=/etc/silicium/orchestrator.env
if [[ ! -f "$ORCHESTRATOR_ENV" ]]; then
  echo "Missing $ORCHESTRATOR_ENV; copy deploy/env/orchestrator.example.env and configure it before installing services." >&2
  exit 1
fi

ensure_env_default() {
  local key="$1"
  local value="$2"
  if ! grep -q -E "^${key}=" "$ORCHESTRATOR_ENV"; then
    printf '%s=%s\n' "$key" "$value" >> "$ORCHESTRATOR_ENV"
  fi
}

# The public URL is the stable HTTPS rendezvous used by desktop nodes.  Keep
# operator-provided values intact while making upgrades converge old env files
# that predate the integrated peer daemon.
ensure_env_default SILICIUM_NODE_ADVERTISE_URL "https://vps-910c1dbc.vps.ovh.net/orchestrator"
ensure_env_default SILICIUM_PEER_SYNC_INTERVAL_S "5"
ensure_env_default SILICIUM_PEER_STALE_AFTER_S "15"
# Migrate the value shipped by the previous integrated-node release. Keep any
# operator-selected value intact while preventing a stale 45-second default
# from surviving upgrades and masking worker disconnects.
if [[ "$(grep -E '^SILICIUM_PEER_STALE_AFTER_S=' "$ORCHESTRATOR_ENV" | tail -n 1 | cut -d= -f2-)" == "45" ]]; then
  sed -i -E 's/^SILICIUM_PEER_STALE_AFTER_S=45$/SILICIUM_PEER_STALE_AFTER_S=15/' "$ORCHESTRATOR_ENV"
fi
unset -f ensure_env_default

sed "s#__SILICIUM_ROOT__#$ROOT#g" deploy/systemd/silicium-orchestrator.service > /etc/systemd/system/silicium-orchestrator.service
sed "s#__SILICIUM_ROOT__#$ROOT#g" deploy/systemd/silicium-update-manifest.service > /etc/systemd/system/silicium-update-manifest.service
sed "s#__SILICIUM_ROOT__#$ROOT#g" deploy/systemd/silicium-experiment-api.service > /etc/systemd/system/silicium-experiment-api.service
cp deploy/systemd/silicium-update-manifest.timer /etc/systemd/system/silicium-update-manifest.timer

if [[ ! -f /etc/silicium/update-channels.env ]]; then
  cp deploy/env/update-channels.example.env /etc/silicium/update-channels.env
fi
# Release identifiers are source-controlled and must follow the artifacts built
# by CI. Preserve operator-specific URLs, keys and cache paths in the existing
# file while refreshing only the channel cadence/version fields.
dev_version="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["version"])' "$ROOT/apps/silicium-node/package.json")"
for release_key in \
  SILICIUM_DEV_VERSION \
  SILICIUM_PROD_VERSION \
  SILICIUM_DEV_CHECK_INTERVAL_SECONDS \
  SILICIUM_PROD_CHECK_INTERVAL_SECONDS \
  SILICIUM_UPDATE_GOSSIP_REQUIRED; do
  if [[ "$release_key" == "SILICIUM_DEV_VERSION" ]]; then
    release_line="SILICIUM_DEV_VERSION=${dev_version}"
  else
    release_line="$(grep -E "^${release_key}=" deploy/env/update-channels.example.env | tail -n 1)"
  fi
  [[ -n "$release_line" ]] || continue
  if grep -q -E "^${release_key}=" /etc/silicium/update-channels.env; then
    sed -i -E "s#^${release_key}=.*#${release_line}#" /etc/silicium/update-channels.env
  else
    printf '%s\n' "$release_line" >> /etc/silicium/update-channels.env
  fi
done
if [[ ! -f /etc/silicium/experiment-api.env ]]; then
  cp deploy/env/experiment-api.example.env /etc/silicium/experiment-api.env
fi
chmod 0755 "$ROOT/deploy/linux/publish-update-manifest.sh"
chmod 0755 "$ROOT/deploy/linux/start-orchestrator.sh"

systemctl daemon-reload
systemctl enable --now silicium-update-manifest.timer
# The unit can already be active from a previous release. Enabling an active
# unit does not reload its changed ExecStart, so explicitly restart it to
# replace the legacy bootstrap server with the integrated node.
systemctl enable silicium-orchestrator.service
systemctl restart silicium-orchestrator.service
# The authenticated experiment/MCP API is a host-side control plane service.
# Keep it enabled so deploy-time health checks and e2e validation can hit the
# real HTTP and RPC endpoints on 46110/9770.
systemctl enable --now silicium-experiment-api.service

echo "Systemd services installed:"
echo "  silicium-orchestrator"
echo "  silicium-update-manifest.timer"
echo "  silicium-experiment-api (installed, host-side systemd service)"
echo "Web/API/dashboard services are owned by deploy/compose/deploy.sh."
