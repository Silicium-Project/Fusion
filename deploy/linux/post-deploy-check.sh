#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/opt/silicium}"
COMPOSE_FILE="$ROOT/deploy/compose/docker-compose.yml"
COMPOSE_ENV="/etc/silicium/compose.env"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/linux/post-deploy-check.sh $ROOT" >&2
  exit 1
fi

[[ -f "$COMPOSE_FILE" ]] || { echo "Missing compose file: $COMPOSE_FILE" >&2; exit 1; }
[[ -f "$COMPOSE_ENV" ]] || { echo "Missing compose env: $COMPOSE_ENV" >&2; exit 1; }

echo "Checking Docker Compose services..."
docker compose --env-file "$COMPOSE_ENV" -f "$COMPOSE_FILE" ps

mapfile -t expected_services < <(docker compose --env-file "$COMPOSE_ENV" -f "$COMPOSE_FILE" config --services)
mapfile -t running_services < <(docker compose --env-file "$COMPOSE_ENV" -f "$COMPOSE_FILE" ps --services --filter status=running)

for service in "${expected_services[@]}"; do
  found=0
  for running in "${running_services[@]}"; do
    if [[ "$running" == "$service" ]]; then
      found=1
      break
    fi
  done
  if [[ "$found" -ne 1 ]]; then
    echo "Service is not running: $service" >&2
    exit 1
  fi
done

echo "Checking local HTTP health endpoints..."
curl -fsS --max-time 8 http://127.0.0.1:8080/health >/dev/null
curl -fsS --max-time 8 http://127.0.0.1:3000 >/dev/null
curl -fsS --max-time 8 http://127.0.0.1:46100/health >/dev/null
curl -fsS --max-time 8 http://127.0.0.1:46110/healthz >/dev/null
curl -fsS --max-time 8 http://127.0.0.1:9091/health >/dev/null
curl -fsS --max-time 8 http://127.0.0.1/downloads/update-manifest.json >/dev/null

echo "Checking node service state..."
if systemctl list-unit-files --type service --all 2>/dev/null | awk '{print $1}' | grep -qx 'silicium-node.service'; then
  systemctl is-active --quiet silicium-node.service
else
  echo "Skipping silicium-node.service check: service is not installed on this host."
fi

echo "Checking deployed release marker..."
[[ -s /var/lib/silicium/releases/current.env ]] || {
  echo "Missing release marker: /var/lib/silicium/releases/current.env" >&2
  exit 1
}

echo "Post-deploy checks passed."
