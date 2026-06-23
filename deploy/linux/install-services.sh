#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/opt/silicium}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/linux/install-services.sh $ROOT" >&2
  exit 1
fi

mkdir -p /etc/silicium /var/lib/silicium/site /var/lib/silicium/network /var/lib/silicium/solana

sed "s#__SILICIUM_ROOT__#$ROOT#g" deploy/systemd/silicium-backend.service > /etc/systemd/system/silicium-backend.service
sed "s#__SILICIUM_ROOT__#$ROOT#g" deploy/systemd/silicium-frontend.service > /etc/systemd/system/silicium-frontend.service
sed "s#__SILICIUM_ROOT__#$ROOT#g" deploy/systemd/silicium-dashboard.service > /etc/systemd/system/silicium-dashboard.service
sed "s#__SILICIUM_ROOT__#$ROOT#g" deploy/systemd/silicium-orchestrator.service > /etc/systemd/system/silicium-orchestrator.service

systemctl daemon-reload

echo "Systemd services installed:"
echo "  silicium-backend"
echo "  silicium-frontend"
echo "  silicium-dashboard"
echo "  silicium-orchestrator"
