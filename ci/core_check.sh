#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE="${CORE_CHECK_MODE:-quick}"            # quick|full
RUN_NATIVE="${CORE_CHECK_NATIVE:-0}"        # 1 to run worker native mode
WITH_DOCKER="${CORE_CHECK_WITH_DOCKER:-auto}" # auto|1|0
REQUIRE_DOCKER="${CORE_CHECK_REQUIRE_DOCKER:-0}"
RUN_DYNAMO="${CORE_CHECK_RUN_DYNAMO:-0}"    # 1 to run worker dynamo mode
CLEAN="${CORE_CHECK_CLEAN:-}"
IN_DOCKER=0
if [[ -f "/.dockerenv" ]]; then
  IN_DOCKER=1
fi
if [[ -z "$CLEAN" ]]; then
  CLEAN=$IN_DOCKER
fi
if [[ "$IN_DOCKER" == "1" ]]; then
  export CPP_TEST_LOCAL=1
  export SMOKE_MODE="${SMOKE_MODE:-container}"
fi

log() {
  echo ">> $*"
}

fail() {
  echo "[ERROR] $*" >&2
  exit 1
}

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

have_docker() {
  have_cmd docker && docker info >/dev/null 2>&1
}

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if have_cmd python3; then
    PYTHON_BIN=python3
  elif have_cmd python; then
    PYTHON_BIN=python
  else
    fail "python3/python not found"
  fi
fi

if ! have_cmd make; then
  fail "make not found"
fi

if [[ "$WITH_DOCKER" == "auto" ]]; then
  if have_docker; then
    WITH_DOCKER=1
  else
    WITH_DOCKER=0
  fi
fi

if [[ "$WITH_DOCKER" == "1" ]] && ! have_docker; then
  if [[ "$REQUIRE_DOCKER" == "1" ]]; then
    fail "docker not available but required"
  fi
  log "Docker not available, optional checks will be skipped."
  WITH_DOCKER=0
fi

SUMMARY_PATH="$ROOT/splitter/run_output/demo/summary.json"

if [[ "$CLEAN" == "1" ]]; then
  log "Clean build (splitter/executor)"
  make -C splitter clean
  make -C executor clean
fi

log "Build + demo (splitter/executor)"
make -C splitter demo

if [[ ! -s "$SUMMARY_PATH" ]]; then
  fail "Missing or empty summary: $SUMMARY_PATH"
fi

log "Build executor"
make -C executor all

log "Build worker"
make -C worker all

log "Worker emu"
(cd worker && ./worker --summary "$SUMMARY_PATH" --mode emu --output json >/dev/null)

if [[ "$RUN_NATIVE" == "1" ]]; then
  log "Worker native (optional)"
  (cd worker && ./worker --summary "$SUMMARY_PATH" --mode native --output json >/dev/null)
fi

if [[ "$RUN_DYNAMO" == "1" ]]; then
  if [[ "$WITH_DOCKER" == "1" ]]; then
    log "Worker dynamo (optional)"
    (cd worker && ./worker --summary "$SUMMARY_PATH" --mode dynamo --output json >/dev/null)
  else
    fail "Requested dynamo check but Docker is not available"
  fi
fi

log "CLI sanity"
./silicium workload list >/dev/null
./silicium workload show calcul/math-simulation --readme >/dev/null

log "Python deps check"
$PYTHON_BIN - <<'PY'
import sys
try:
    import pytest  # noqa: F401
    import yaml    # noqa: F401
except Exception as exc:
    print(f"Missing python deps: {exc}", file=sys.stderr)
    raise SystemExit(1)
PY

log "Pytest"
$PYTHON_BIN -m pytest

if [[ "$MODE" == "full" ]]; then
  log "C++ tests (splitter)"
  make -C splitter test
  log "C++ tests (executor)"
  make -C executor test
  log "C++ tests (worker)"
  make -C worker test

  if [[ "$WITH_DOCKER" == "1" ]]; then
    log "Proxy smoke (Docker)"
    ./silicium smoke
  else
    log "Skipping proxy smoke (Docker unavailable)"
  fi
fi

log "Core check OK"
