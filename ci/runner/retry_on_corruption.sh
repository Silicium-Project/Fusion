#!/usr/bin/env bash
# Run a build command; if it fails because the runner's build state is
# corrupted, clean that state and try exactly once more.
#
# Usage: retry_on_corruption.sh [--target-dir DIR] -- <command> [args...]
#   --target-dir  build directory to delete on corruption (default: target)
#
# Handled corruptions (self-hosted runner reusing its workspace and ~/.cargo):
# - target/ files deleted during or between builds: "could not parse/generate
#   dep info", "can't find crate for" (E0463), "found possibly newer version";
# - a crate source in ~/.cargo/registry/src with missing files: a C build
#   (cc-rs) failing on a registry path.
# Any other failure (a real compile or test error) is returned unchanged.
#
# The runners share ~/.cargo and ~/.rustup: another job may be reinstalling
# rustup at the moment of the retry (the binary is then missing for a few
# seconds). Before retrying, wait for the shared Rust install lock and for the
# command to be back, instead of failing with "command not found".
set -euo pipefail

target_dir="target"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --target-dir) target_dir="$2"; shift 2 ;;
    --) shift; break ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done
[[ $# -gt 0 ]] || { echo "missing command" >&2; exit 2; }

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
log="$(mktemp)"
trap 'rm -f "$log"' EXIT

run() {
  set +e
  "$@" 2>&1 | tee "$log"
  local status=${PIPESTATUS[0]}
  set -e
  return "$status"
}

# Waits until no job is installing Rust (shared lock of install_rust_toolchain.sh)
# and `$1` can be run again; fails with a clear message after
# RETRY_COMMAND_WAIT_S seconds (default 120).
wait_for_command() {
  local command_name="$1"
  local lock="${RUSTUP_HOME:-$HOME/.rustup}/.silicium-install.lock"
  if [[ -e "$lock" ]] && command -v flock >/dev/null 2>&1; then
    exec 8<"$lock"
    flock -s -w 900 8 || echo "::warning::Rust install lock still held after 15 min."
    exec 8<&-
  fi
  local deadline=$((SECONDS + ${RETRY_COMMAND_WAIT_S:-120}))
  while ((SECONDS < deadline)); do
    hash -r
    if command -v "$command_name" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  echo "::error::'$command_name' is missing from PATH for $(id -un) (HOME=$HOME): another job probably removed or reinstalled it; re-run this job." >&2
  return 127
}

status=0
run "$@" || status=$?
if [[ "$status" -eq 0 ]]; then
  exit 0
fi

target_corrupted='could not parse/generate dep info|error\[E0463\]|can.t find crate for|found possibly newer version of crate'
source_corrupted='error occurred in cc-rs|No such file or directory.*registry/src'
if grep -Eq "$target_corrupted" "$log"; then
  echo "::warning::Corrupted build directory detected; deleting $target_dir and retrying once."
  rm -rf -- "$target_dir"
elif grep -Eq "$source_corrupted" "$log" && grep -q '/registry/src/' "$log"; then
  echo "::warning::Possibly incomplete Cargo sources; re-checking them and retrying once."
  python3 "$script_dir/repair_cargo_sources.py"
else
  exit "$status"
fi
wait_for_command "$1"
run "$@"
