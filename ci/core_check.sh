#!/usr/bin/env bash
# Main check of the Network repository (`make check`, Fusion "network-core"):
# Rust workspace tests, then the tests of the Python developer tooling.
#
# CORE_CHECK_MODE=full also runs the end-to-end network check (ci/e2e.sh).
# CORE_CHECK_SCOPE is accepted for compatibility (platform|all) and has no
# other effect: there is a single scope since the Python runtime is gone.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE="${CORE_CHECK_MODE:-quick}"
SCOPE="${CORE_CHECK_SCOPE:-platform}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

log() { echo ">> $*"; }
fail() { echo "[ERROR] $*" >&2; exit 1; }

case "$MODE" in quick|full) ;; *) fail "Unknown CORE_CHECK_MODE: $MODE (expected quick or full)" ;; esac
case "$SCOPE" in platform|all) ;; *) fail "Unknown CORE_CHECK_SCOPE: $SCOPE (expected platform or all)" ;; esac
command -v cargo >/dev/null 2>&1 || fail "cargo not found"

log "Rust tests (workspace)"
cargo test --workspace --locked

if command -v "$PYTHON_BIN" >/dev/null 2>&1 && "$PYTHON_BIN" -c 'import pytest' 2>/dev/null; then
  log "Developer tooling tests"
  "$PYTHON_BIN" -m pytest -q
else
  echo "pytest unavailable; developer tooling tests skipped (pip install -r requirements-dev.txt)."
fi

if [[ "$MODE" == "full" ]]; then
  log "End-to-end network check"
  bash ci/e2e.sh
fi

log "Core check OK"
