#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/opt/silicium}"
COMPOSE_FILE="$ROOT/deploy/compose/docker-compose.yml"
COMPOSE_ENV="/etc/silicium/compose.env"
APP_PACKAGE_JSON="$ROOT/apps/silicium-node/package.json"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/compose/deploy.sh $ROOT" >&2
  exit 1
fi

[[ -f "$COMPOSE_FILE" ]] || { echo "Missing compose file: $COMPOSE_FILE" >&2; exit 1; }
[[ -f "$COMPOSE_ENV" ]] || { echo "Missing compose env: $COMPOSE_ENV" >&2; exit 1; }
[[ -f "$APP_PACKAGE_JSON" ]] || { echo "Missing app package: $APP_PACKAGE_JSON" >&2; exit 1; }

# The orchestrator participates in peer telemetry even though it is not a
# desktop binary. Derive its version from the same canonical package used to
# build installers so the web directory never reports a stale hard-coded value.
if [[ -z "${SILICIUM_APP_VERSION:-}" ]]; then
  SILICIUM_APP_VERSION="$(sed -nE 's/^[[:space:]]*"version"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/p' "$APP_PACKAGE_JSON" | head -n 1)"
fi
[[ -n "$SILICIUM_APP_VERSION" ]] || { echo "Could not derive SILICIUM_APP_VERSION" >&2; exit 1; }
export SILICIUM_APP_VERSION
export SILICIUM_RELEASE_CHANNEL="${SILICIUM_RELEASE_CHANNEL:-dev}"
export SILICIUM_RELEASE_BUILD="${SILICIUM_RELEASE_BUILD:-$(git -C "$ROOT" rev-parse --short=12 HEAD)}"

# Older installations ran these processes as host systemd services. Compose is
# now the single owner of their ports; stop and disable stale units before
# recreating containers so 46100 and the web ports cannot remain occupied.
for legacy_unit in \
  silicium-backend.service \
  silicium-frontend.service \
  silicium-dashboard.service \
  silicium-orchestrator.service \
  silicium-experiment-api.service; do
  systemctl disable --now "$legacy_unit" 2>/dev/null || true
done

docker compose --env-file "$COMPOSE_ENV" -f "$COMPOSE_FILE" up -d --build --remove-orphans
# Nginx resolves Compose service names at startup; recreate it after app
# containers so its upstream IPs cannot remain stale after a deployment.
docker compose --env-file "$COMPOSE_ENV" -f "$COMPOSE_FILE" up -d --force-recreate proxy
docker compose --env-file "$COMPOSE_ENV" -f "$COMPOSE_FILE" ps
