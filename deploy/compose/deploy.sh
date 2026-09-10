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
# desktop binary. Prefer the CI/CD release version when provided, otherwise
# derive from the canonical desktop package.
if [[ -z "${SILICIUM_APP_VERSION:-}" ]] && [[ -n "${SILICIUM_RELEASE_VERSION:-}" ]]; then
  SILICIUM_APP_VERSION="$SILICIUM_RELEASE_VERSION"
fi
if [[ -z "${SILICIUM_APP_VERSION:-}" ]]; then
  SILICIUM_APP_VERSION="$(sed -nE 's/^[[:space:]]*"version"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/p' "$APP_PACKAGE_JSON" | head -n 1)"
fi
[[ -n "$SILICIUM_APP_VERSION" ]] || { echo "Could not derive SILICIUM_APP_VERSION" >&2; exit 1; }
export SILICIUM_APP_VERSION
export SILICIUM_RELEASE_CHANNEL="${SILICIUM_RELEASE_CHANNEL:-dev}"
export SILICIUM_RELEASE_BUILD="${SILICIUM_RELEASE_BUILD:-$(git -C "$ROOT" rev-parse --short=12 HEAD)}"

compose=(docker compose --env-file "$COMPOSE_ENV" -f "$COMPOSE_FILE")

# The backend image deliberately runs as an unprivileged user while the
# persistent bind mount is created by root on the host. Resolve the image's
# effective UID/GID after building it and give only the jobs directory to that
# user. Without this step, CreateJob cannot create <job-id>/input and returns
# "Could not create job input directory".
"${compose[@]}" build backend
# `docker compose images -q` reports the image attached to an existing
# container. During a rolling deploy that container can retain a deleted
# digest even after the fresh build succeeds. Inspect the explicit image tag
# produced by this compose file instead.
backend_image="silicium-backend:latest"
backend_image_id="$(docker image inspect --format '{{.Id}}' "$backend_image")"
[[ -n "$backend_image_id" ]] || { echo "Could not resolve the built backend image." >&2; exit 1; }
backend_identity="$(docker run --rm --entrypoint sh "$backend_image_id" -c 'printf "%s:%s" "$(id -u)" "$(id -g)"')"
[[ "$backend_identity" =~ ^[0-9]+:[0-9]+$ ]] || {
  echo "Could not resolve backend UID/GID: $backend_identity" >&2
  exit 1
}
backend_uid="${backend_identity%%:*}"
backend_gid="${backend_identity##*:}"
install -d -m 0750 -o "$backend_uid" -g "$backend_gid" /var/lib/silicium/site/jobs /var/lib/silicium/site/runtime

# The orchestrator runs on the host and keeps its private identity key mode
# 0600. The API container must sign task-control messages as the same identity,
# but it must not receive the host service's key path directly. Maintain a
# private, UID-scoped copy for the unprivileged backend user.
orchestrator_identity_dir="/var/lib/silicium/network/orchestrator/state"
orchestrator_identity="$orchestrator_identity_dir/peer_identity_ed25519.pem"
orchestrator_public_identity="$orchestrator_identity_dir/peer_identity_ed25519.pub.pem"
backend_identity_dir="/var/lib/silicium/network/orchestrator/backend-identity"
for _ in $(seq 1 30); do
  if [[ -f "$orchestrator_identity" && -f "$orchestrator_public_identity" ]]; then
    break
  fi
  sleep 1
done
if [[ ! -f "$orchestrator_identity" || ! -f "$orchestrator_public_identity" ]]; then
  echo "Orchestrator identity key was not created at $orchestrator_identity" >&2
  exit 1
fi
install -d -m 0750 -o "$backend_uid" -g "$backend_gid" "$backend_identity_dir"
install -o "$backend_uid" -g "$backend_gid" -m 0600 "$orchestrator_identity" "$backend_identity_dir/peer_identity_ed25519.pem"
install -o "$backend_uid" -g "$backend_gid" -m 0644 "$orchestrator_public_identity" "$backend_identity_dir/peer_identity_ed25519.pub.pem"

# Older installations ran these processes as host systemd services. Compose is
# now the single owner of the web and API ports; stop and disable the stale
# host services before recreating containers so 3000, 5174 and 8080 cannot
# remain occupied. The orchestrator stays on the host because it owns 46100.
# The authenticated experiment/MCP API is also a host-side systemd service and
# must stay enabled for deploy-time checks and e2e validation on 46110/9770.
for legacy_unit in \
  silicium-backend.service \
  silicium-frontend.service \
  silicium-dashboard.service; do
  systemctl disable --now "$legacy_unit" 2>/dev/null || true
done

"${compose[@]}" up -d --build --remove-orphans
# Nginx resolves Compose service names at startup; recreate it after app
# containers so its upstream IPs cannot remain stale after a deployment.
"${compose[@]}" up -d --force-recreate proxy
"${compose[@]}" ps
"$ROOT/deploy/linux/publish-update-manifest.sh"
