#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/opt/silicium}"
COMPOSE_FILE="$ROOT/deploy/compose/docker-compose.yml"
COMPOSE_ENV="/etc/silicium/compose.env"
BACKEND_ENV="/etc/silicium/backend.env"
BACKUP_DIR="/var/lib/silicium/backups/postgres"
DATA_DIR="/var/lib/silicium/postgres"
SQLITE_PATH="${SQLITE_PATH:-/var/lib/silicium/site/silicium.db}"

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
if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose v2 is required." >&2
  exit 1
fi

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
SQLITE_BACKUP_FILE="$BACKUP_DIR/legacy-$(date -u +%Y%m%dT%H%M%SZ).sqlite"

if [[ -f "$SQLITE_PATH" ]]; then
  if ! command -v sqlite3 >/dev/null 2>&1; then
    echo "sqlite3 is required to migrate $SQLITE_PATH." >&2
    exit 1
  fi
  if [[ "$(sqlite3 "$SQLITE_PATH" 'PRAGMA integrity_check;')" != "ok" ]]; then
    echo "SQLite integrity check failed: $SQLITE_PATH" >&2
    exit 1
  fi
  if ! sqlite3 "$SQLITE_PATH" "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users';" | grep -q '^1$'; then
    echo "SQLite database has no users table: $SQLITE_PATH" >&2
    exit 1
  fi
  LEGACY_TABLES="$(sqlite3 "$SQLITE_PATH" "SELECT group_concat(name, ', ') FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT IN ('users', 'jobs');")"
  if [[ -n "$LEGACY_TABLES" ]]; then
    echo "Unsupported legacy SQLite tables detected: $LEGACY_TABLES" >&2
    echo "Migration stopped to prevent data loss. Export these tables before retrying." >&2
    exit 1
  fi
  SQLITE_USER_COUNT="$(sqlite3 "$SQLITE_PATH" 'SELECT count(*) FROM users;')"
  SQLITE_JOB_COUNT="$(sqlite3 "$SQLITE_PATH" 'SELECT count(*) FROM jobs;')"
  cp --preserve=all "$SQLITE_PATH" "$SQLITE_BACKUP_FILE"
  systemctl stop silicium-backend 2>/dev/null || true
fi

if [[ -f "$SQLITE_PATH" ]]; then
  : "SQLite is the explicitly detected legacy source."
elif systemctl is-active --quiet postgresql; then
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
elif [[ ! -f "$SQLITE_PATH" ]]; then
  echo "No running PostgreSQL service or container was detected." >&2
  exit 1
fi

if [[ -f "$BACKUP_FILE" ]]; then
  if [[ ! -s "$BACKUP_FILE" ]] || ! pg_restore --list "$BACKUP_FILE" | grep -q 'TABLE DATA'; then
    echo "The PostgreSQL dump is missing or contains no table data: $BACKUP_FILE" >&2
    exit 1
  fi
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

if [[ -f "$BACKUP_FILE" ]]; then
  "${COMPOSE[@]}" exec -T postgres pg_restore \
    --clean --if-exists --no-owner \
    -U "$POSTGRES_USER" -d "$POSTGRES_DB" < "$BACKUP_FILE"
fi

if [[ -f "$SQLITE_PATH" ]]; then
  SCHEMA_FILE="$ROOT/BackEnd/Database/schema.sql"
  if [[ ! -f "$SCHEMA_FILE" ]]; then
    echo "PostgreSQL schema file not found: $SCHEMA_FILE" >&2
    exit 1
  fi
  "${COMPOSE[@]}" exec -T postgres psql -v ON_ERROR_STOP=1 \
    -U "$POSTGRES_USER" -d "$POSTGRES_DB" < "$SCHEMA_FILE"
  SQLITE_CSV="$BACKUP_DIR/users-$(date -u +%Y%m%dT%H%M%SZ).csv"
  sqlite3 "$SQLITE_PATH" <<'SQL' > "$SQLITE_CSV"
.mode csv
.headers off
.nullvalue \N
SELECT id, first_name, last_name, email, password_hash, username,
       wallet_address, role, created_at, updated_at
FROM users;
SQL
  "${COMPOSE[@]}" exec -T postgres psql -v ON_ERROR_STOP=1 \
    -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -c "\\copy users (id, first_name, last_name, email, password_hash, username, wallet_address, role, created_at, updated_at) FROM STDIN WITH (FORMAT csv, NULL '\\N')" < "$SQLITE_CSV"
  POSTGRES_USER_COUNT="$("${COMPOSE[@]}" exec -T postgres psql -Atqc 'SELECT count(*) FROM users;' -U "$POSTGRES_USER" -d "$POSTGRES_DB" | tr -d '\r')"
  if [[ "$POSTGRES_USER_COUNT" != "$SQLITE_USER_COUNT" ]]; then
    echo "User count mismatch after SQLite migration: SQLite=$SQLITE_USER_COUNT PostgreSQL=$POSTGRES_USER_COUNT" >&2
    exit 1
  fi
  "${COMPOSE[@]}" exec -T postgres psql -v ON_ERROR_STOP=1 \
    -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -c "\\copy jobs (id, user_id, title, description, workload, priority, status, silicium_job_id, input_path, result_path, summary_path, devnet_trace_path, devnet_job, dashboard_url, error_message, started_at, completed_at, created_at, updated_at) FROM STDIN WITH (FORMAT csv, NULL '\\N')" < <(
      sqlite3 "$SQLITE_PATH" <<'SQL'
.mode csv
.headers off
.nullvalue \N
SELECT id, user_id, title, description, workload, priority, status,
       silicium_job_id, input_path, result_path, summary_path,
       devnet_trace_path, devnet_job, dashboard_url, error_message,
       started_at, completed_at, created_at, updated_at
FROM jobs;
SQL
    )
  POSTGRES_JOB_COUNT="$("${COMPOSE[@]}" exec -T postgres psql -Atqc 'SELECT count(*) FROM jobs;' -U "$POSTGRES_USER" -d "$POSTGRES_DB" | tr -d '\r')"
  if [[ "$POSTGRES_JOB_COUNT" != "$SQLITE_JOB_COUNT" ]]; then
    echo "Job count mismatch after SQLite migration: SQLite=$SQLITE_JOB_COUNT PostgreSQL=$POSTGRES_JOB_COUNT" >&2
    exit 1
  fi
  "${COMPOSE[@]}" exec -T postgres psql -v ON_ERROR_STOP=1 \
    -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -c "SELECT setval(pg_get_serial_sequence('users', 'id'), COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM users; SELECT setval(pg_get_serial_sequence('jobs', 'id'), COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM jobs;"
fi

"${COMPOSE[@]}" up -d --build

if systemctl list-unit-files postgresql.service >/dev/null 2>&1; then
  systemctl disable postgresql 2>/dev/null || true
  systemctl stop postgresql 2>/dev/null || true
fi
for service in silicium-backend silicium-frontend silicium-dashboard silicium-orchestrator nginx; do
  systemctl disable "$service" 2>/dev/null || true
done

if [[ -f "$SQLITE_PATH" ]]; then
  if ! "${COMPOSE[@]}" ps --status running --services | grep -qx 'backend'; then
    echo "The PostgreSQL-backed backend is not running; keeping the SQLite source." >&2
    exit 1
  fi
  if [[ -f "$BACKEND_ENV" ]]; then
    cp --preserve=all "$BACKEND_ENV" "$BACKUP_DIR/backend.env.pre-postgres-$(date -u +%Y%m%dT%H%M%SZ)"
    sed -i '/^DATABASE_DRIVER=/d; /^SQLITE_PATH=/d' "$BACKEND_ENV"
  fi
  rm -f "$SQLITE_PATH"
fi

echo "PostgreSQL migration completed; SQLite is no longer active."
[[ -f "$BACKUP_FILE" ]] && echo "PostgreSQL backup: $BACKUP_FILE"
[[ -f "$SQLITE_BACKUP_FILE" ]] && echo "SQLite backup: $SQLITE_BACKUP_FILE"
echo "Stack: ${COMPOSE[*]} ps"
