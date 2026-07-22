#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/opt/silicium}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/linux/install-services.sh $ROOT" >&2
  exit 1
fi

[[ -d "$ROOT/deploy/systemd" ]] || { echo "Missing deployment files under: $ROOT" >&2; exit 1; }
cd "$ROOT"

mkdir -p /etc/silicium /var/lib/silicium/site /var/lib/silicium/network /var/lib/silicium/solana /var/lib/silicium/downloads

sed "s#__SILICIUM_ROOT__#$ROOT#g" deploy/systemd/silicium-backend.service > /etc/systemd/system/silicium-backend.service
sed "s#__SILICIUM_ROOT__#$ROOT#g" deploy/systemd/silicium-frontend.service > /etc/systemd/system/silicium-frontend.service
sed "s#__SILICIUM_ROOT__#$ROOT#g" deploy/systemd/silicium-dashboard.service > /etc/systemd/system/silicium-dashboard.service
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
for release_key in \
  SILICIUM_DEV_VERSION \
  SILICIUM_PROD_VERSION \
  SILICIUM_DEV_CHECK_INTERVAL_SECONDS \
  SILICIUM_PROD_CHECK_INTERVAL_SECONDS; do
  release_line="$(grep -E "^${release_key}=" deploy/env/update-channels.example.env | tail -n 1)"
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

systemctl daemon-reload
systemctl enable --now silicium-update-manifest.timer
systemctl enable --now silicium-experiment-api.service

echo "Systemd services installed:"
echo "  silicium-backend"
echo "  silicium-frontend"
echo "  silicium-dashboard"
echo "  silicium-orchestrator"
echo "  silicium-update-manifest.timer"
echo "  silicium-experiment-api"
