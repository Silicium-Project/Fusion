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
run "$@"
