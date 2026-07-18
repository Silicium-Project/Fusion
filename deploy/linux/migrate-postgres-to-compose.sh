#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/opt/silicium}"
COMPOSE_FILE="$ROOT/deploy/compose/docker-compose.yml"
COMPOSE_ENV="/etc/silicium/compose.env"
BACKUP_DIR="/var/lib/silicium/backups/postgres"
DATA_DIR="/var/lib/silicium/postgres"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/linux/migrate-postgres-to-compose.sh $ROOT" >&2
  exit 1
fi

for required in docker "$COMPOSE_FILE" "$COMPOSE_ENV"; do
  if [[ ! -e "$required" ]] && ! command -v "$required" >/dev/null 2>&1; then
    echo "Missing migration prerequisite: $required" >&2
    exit 1
  fi
done

set -a
# shellcheck disable=SC1091
source "$COMPOSE_ENV"
# shellcheck disable=SC1091
set +a

: "${POSTGRES_DB:?POSTGRES_DB is required in /etc/silicium/compose.env}"
: "${POSTGRES_USER:?POSTGRES_USER is required in /etc/silicium/compose.env}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required in /etc/silicium/compose.env}"
SOURCE_POSTGRES_DB="${SOURCE_POSTGRES_DB:-$POSTGRES_DB}"

if [[ -e "$DATA_DIR" ]] && [[ -n "$(find "$DATA_DIR" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  echo "Refusing to use non-empty PostgreSQL data directory: $DATA_DIR" >&2
  echo "The migration is intentionally non-destructive; move it aside only after a verified backup." >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR" "$DATA_DIR"
BACKUP_FILE="$BACKUP_DIR/legacy-$(date -u +%Y%m%dT%H%M%SZ).dump"

if systemctl is-active --quiet postgresql; then
  if ! command -v pg_dump >/dev/null 2>&1 || ! command -v psql >/dev/null 2>&1; then
    echo "pg_dump is required to export the existing PostgreSQL service." >&2
    exit 1
  fi
  if ! sudo -u postgres psql -Atqc "SELECT 1 FROM pg_database WHERE datname='$SOURCE_POSTGRES_DB'" | grep -q '^1$'; then
    echo "Existing PostgreSQL database not found: $SOURCE_POSTGRES_DB" >&2
    sudo -u postgres psql -Atqc "SELECT datname FROM pg_database WHERE datistemplate = false" >&2 || true
    exit 1
  fi
  sudo -u postgres pg_dump --dbname="$SOURCE_POSTGRES_DB" --format=custom > "$BACKUP_FILE"
elif [[ -n "$(docker ps --filter ancestor=postgres --format '{{.ID}}' | head -n 1)" ]]; then
  echo "A PostgreSQL container was detected, but automatic credentials are not guessed." >&2
  echo "Export it with pg_dump, verify the dump, then rerun this migration." >&2
  exit 1
else
  echo "No running PostgreSQL service or container was detected." >&2
  exit 1
fi

if [[ ! -s "$BACKUP_FILE" ]] || ! pg_restore --list "$BACKUP_FILE" | grep -q 'TABLE DATA'; then
  echo "The PostgreSQL dump is missing or contains no table data: $BACKUP_FILE" >&2
  exit 1
fi

systemctl stop silicium-backend silicium-frontend silicium-dashboard silicium-orchestrator nginx 2>/dev/null || true

COMPOSE=(docker compose --env-file "$COMPOSE_ENV" -f "$COMPOSE_FILE")
"${COMPOSE[@]}" up -d postgres

for attempt in $(seq 1 30); do
  if "${COMPOSE[@]}" exec -T postgres pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1; then
    break
  fi
  if [[ "$attempt" -eq 30 ]]; then
    echo "The containerized PostgreSQL service did not become ready." >&2
    exit 1
  fi
  sleep 2
done

"${COMPOSE[@]}" exec -T postgres pg_restore \
  --clean --if-exists --no-owner \
  -U "$POSTGRES_USER" -d "$POSTGRES_DB" < "$BACKUP_FILE"

"${COMPOSE[@]}" up -d --build

if systemctl list-unit-files postgresql.service >/dev/null 2>&1; then
  systemctl disable postgresql 2>/dev/null || true
  systemctl stop postgresql 2>/dev/null || true
fi
for service in silicium-backend silicium-frontend silicium-dashboard silicium-orchestrator nginx; do
  systemctl disable "$service" 2>/dev/null || true
done

echo "PostgreSQL migration completed without deleting the legacy database."
echo "Backup: $BACKUP_FILE"
echo "Stack: ${COMPOSE[*]} ps"
