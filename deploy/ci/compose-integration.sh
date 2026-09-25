#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
COMPOSE_FILE="$ROOT/deploy/compose/docker-compose.integration.yml"
RUN_ID="${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-0}"
PROJECT="silicium-integration-${RUN_ID//[^a-zA-Z0-9]/-}"

[[ -f "$COMPOSE_FILE" ]] || { echo "Missing integration Compose file: $COMPOSE_FILE" >&2; exit 1; }

cd "$ROOT"

cleanup() {
  docker compose --project-name "$PROJECT" --file "$COMPOSE_FILE" down --volumes --remove-orphans || true
}

set +e
docker compose --project-name "$PROJECT" --file "$COMPOSE_FILE" up \
  --build \
  --abort-on-container-exit \
  --exit-code-from integration-gate \
  integration-gate
status=$?
set -e

if [[ "$status" -ne 0 ]]; then
  echo "::error title=Compose integration gate failed::integration-gate exited with status $status"
  docker compose --project-name "$PROJECT" --file "$COMPOSE_FILE" ps --all || true
  docker compose --project-name "$PROJECT" --file "$COMPOSE_FILE" logs --no-color --timestamps \
    integration-gate proxy frontend backend silicium-node compute-daemon reputation-bridge || true
fi

cleanup
exit "$status"
