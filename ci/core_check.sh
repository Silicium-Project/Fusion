#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE="${CORE_CHECK_MODE:-quick}"
SCOPE="${CORE_CHECK_SCOPE:-platform}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
DOCKER_MODE="${CORE_CHECK_WITH_DOCKER:-auto}"
REQUIRE_DOCKER="${CORE_CHECK_REQUIRE_DOCKER:-0}"

log() {
  echo ">> $*"
}

fail() {
  echo "[ERROR] $*" >&2
  exit 1
}

case "$MODE" in
  quick|full) ;;
  *) fail "Unknown CORE_CHECK_MODE: $MODE (expected quick or full)" ;;
esac

case "$SCOPE" in
  platform|all) ;;
  *) fail "Unknown CORE_CHECK_SCOPE: $SCOPE (expected platform)" ;;
esac

command -v "$PYTHON_BIN" >/dev/null 2>&1 || fail "Python executable not found: $PYTHON_BIN"

log "Python syntax"
"$PYTHON_BIN" -m compileall -q tools workloads tests

log "Workload manifests"
"$PYTHON_BIN" ./silicium workload lint
"$PYTHON_BIN" ./silicium workload golden --strict

log "Python tests"
"$PYTHON_BIN" -m pytest

log "Raytracer native tests"
if command -v cargo >/dev/null 2>&1; then
  cargo test --manifest-path workloads/raytracer/native/Cargo.toml
else
  echo "Cargo unavailable; native raytracer tests skipped."
fi

if [[ "$MODE" == "full" ]]; then
  if [[ "$DOCKER_MODE" == "0" ]]; then
    echo "Docker-backed checks disabled."
  elif command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    log "Proxy smoke"
    "$PYTHON_BIN" ./silicium smoke
  elif [[ "$REQUIRE_DOCKER" == "1" || "$DOCKER_MODE" == "1" ]]; then
    fail "Docker is required for the full check but is unavailable."
  else
    echo "Docker unavailable; proxy smoke skipped."
  fi
fi

log "Core check OK"
