#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE="${CORE_CHECK_MODE:-quick}"            # quick|full
RUN_NATIVE="${CORE_CHECK_NATIVE:-0}"        # 1 to run worker native mode
WITH_DOCKER="${CORE_CHECK_WITH_DOCKER:-auto}" # auto|1|0
REQUIRE_DOCKER="${CORE_CHECK_REQUIRE_DOCKER:-0}"
RUN_DYNAMO="${CORE_CHECK_RUN_DYNAMO:-0}"    # 1 to run worker dynamo mode
SCOPE="${CORE_CHECK_SCOPE:-all}"            # all|splitter|executor|worker
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

CORE_CHECK_JOBS="${CORE_CHECK_JOBS:-}"
if [[ -n "$CORE_CHECK_JOBS" ]]; then
  export JOBS="$CORE_CHECK_JOBS"
  log "Using JOBS=$JOBS"
fi

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

have_docker() {
  have_cmd docker && docker info >/dev/null 2>&1
}

case "$SCOPE" in
  all|splitter|executor|worker) ;;
  *)
    fail "Unknown CORE_CHECK_SCOPE: $SCOPE"
    ;;
esac

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
WORKER_SUMMARY_PATH="$ROOT/demo/worker/summary.json"

RUN_SPLITTER=0
RUN_EXECUTOR=0
RUN_WORKER=0
RUN_CLI=0
RUN_PYTHON=0
RUN_PYTEST=0
RUN_SMOKE=0

case "$SCOPE" in
  all)
    RUN_SPLITTER=1
    RUN_EXECUTOR=1
    RUN_WORKER=1
    RUN_CLI=1
    RUN_PYTHON=1
    RUN_PYTEST=1
    RUN_SMOKE=1
    ;;
  splitter)
    RUN_SPLITTER=1
    ;;
  executor)
    RUN_EXECUTOR=1
    ;;
  worker)
    RUN_WORKER=1
    ;;
esac

if [[ "$CLEAN" == "1" ]]; then
  log "Clean build (scope: $SCOPE)"
  if [[ "$RUN_SPLITTER" == "1" ]]; then
    make -C splitter clean
  fi
  if [[ "$RUN_EXECUTOR" == "1" ]]; then
    make -C executor clean
  fi
  if [[ "$RUN_WORKER" == "1" ]]; then
    make -C worker clean
  fi
fi

if [[ "$SCOPE" == "all" ]]; then
  log "Build + demo (splitter/executor)"
  make -C splitter demo

  if [[ ! -s "$SUMMARY_PATH" ]]; then
    fail "Missing or empty summary: $SUMMARY_PATH"
  fi
  if [[ "$RUN_WORKER" == "1" ]]; then
    log "Build worker"
    make -C worker all
  fi
else
  if [[ "$RUN_SPLITTER" == "1" ]]; then
    log "Build splitter"
    make -C splitter all
  fi

  if [[ "$RUN_EXECUTOR" == "1" ]]; then
    log "Build executor"
    make -C executor all
  fi

  if [[ "$RUN_WORKER" == "1" ]]; then
    if [[ "$RUN_EXECUTOR" != "1" ]]; then
      log "Build executor (dependency for worker)"
      make -C executor all
    fi
    log "Build worker"
    make -C worker all
  fi
fi

if [[ "$RUN_WORKER" == "1" ]]; then
  if [[ "$SCOPE" == "all" ]]; then
    WORKER_SUMMARY="$SUMMARY_PATH"
  else
    WORKER_SUMMARY="$WORKER_SUMMARY_PATH"
  fi

  if [[ ! -s "$WORKER_SUMMARY" ]]; then
    fail "Missing or empty summary: $WORKER_SUMMARY"
  fi

  log "Worker emu"
  (cd worker && ./worker --summary "$WORKER_SUMMARY" --mode emu --output json >/dev/null)
fi

if [[ "$RUN_NATIVE" == "1" ]]; then
  if [[ "$RUN_WORKER" == "1" ]]; then
    log "Worker native (optional)"
    (cd worker && ./worker --summary "$WORKER_SUMMARY" --mode native --output json >/dev/null)
  else
    log "Skipping worker native (scope: $SCOPE)"
  fi
fi

if [[ "$RUN_DYNAMO" == "1" ]]; then
  if [[ "$RUN_WORKER" == "1" ]]; then
    if [[ "$WITH_DOCKER" == "1" ]]; then
      log "Worker dynamo (optional)"
      (cd worker && ./worker --summary "$WORKER_SUMMARY" --mode dynamo --output json >/dev/null)
    else
      fail "Requested dynamo check but Docker is not available"
    fi
  else
    log "Skipping worker dynamo (scope: $SCOPE)"
  fi
fi

if [[ "$RUN_CLI" == "1" ]]; then
  log "CLI sanity"
  ./silicium workload list >/dev/null
  ./silicium workload show calcul/math-simulation --readme >/dev/null
fi

if [[ "$RUN_PYTHON" == "1" ]]; then
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
fi

if [[ "$RUN_PYTEST" == "1" ]]; then
  log "Pytest"
  $PYTHON_BIN -m pytest
fi

if [[ "$MODE" == "full" ]]; then
  if [[ "$RUN_SPLITTER" == "1" ]]; then
    log "C++ tests (splitter)"
    make -C splitter test
  fi
  if [[ "$RUN_EXECUTOR" == "1" ]]; then
    log "C++ tests (executor)"
    make -C executor test
  fi
  if [[ "$RUN_WORKER" == "1" ]]; then
    log "C++ tests (worker)"
    make -C worker test
  fi

  if [[ "$RUN_SMOKE" == "1" ]]; then
    if [[ "$WITH_DOCKER" == "1" ]]; then
      log "Proxy smoke (Docker)"
      ./silicium smoke
    else
      log "Skipping proxy smoke (Docker unavailable)"
    fi
  fi
fi

log "Core check OK"
