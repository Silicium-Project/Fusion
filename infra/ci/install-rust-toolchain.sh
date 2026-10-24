#!/usr/bin/env bash
# Install (or update) a rustup toolchain on a self-hosted runner, one job at a time.
#
# Usage: install-rust-toolchain.sh <toolchain> [component,...]
#
# The runners on the VPS share one ~/.rustup. When a new stable Rust is
# released, every job starting at that moment updates the same toolchain and
# they break each other's downloads ("could not rename 'downloaded' file ...
# .partial"). This takes an exclusive lock on the rustup home (waits up to
# 15 min), installs, retries twice on a failed download, and sets `stable` as
# the default toolchain like dtolnay/rust-toolchain did. It uses the same lock
# file as Network/ci/runner/install_rust_toolchain.sh, so Fusion and Network
# jobs wait for each other.
set -euo pipefail

toolchain="${1:?toolchain required}"
components="${2:-}"
cargo_bin="${CARGO_HOME:-$HOME/.cargo}/bin"
rustup_home="${RUSTUP_HOME:-$HOME/.rustup}"

args=(toolchain install "$toolchain" --profile minimal --no-self-update)
if [[ -n "$components" ]]; then
  args+=(--component "$components")
fi

mkdir -p "$rustup_home"
exec 9>"$rustup_home/.silicium-install.lock"
if ! flock -w 900 9; then
  echo "Timed out waiting for another job to finish installing Rust." >&2
  exit 1
fi

# Some runners (other user accounts) have no rustup yet: install it the way
# dtolnay/rust-toolchain did, without touching shell profiles.
if [[ -x "$cargo_bin/rustup" ]]; then
  rustup="$cargo_bin/rustup"
elif command -v rustup >/dev/null 2>&1; then
  rustup="$(command -v rustup)"
else
  echo "rustup not found for $(id -un) (HOME=$HOME); installing it."
  curl --proto '=https' --tlsv1.2 --retry 3 -sSf https://sh.rustup.rs \
    | sh -s -- -y --default-toolchain none --profile minimal --no-modify-path
  rustup="$cargo_bin/rustup"
fi
echo "Using $rustup for $(id -un)"

for attempt in 1 2 3; do
  if "$rustup" "${args[@]}"; then
    break
  fi
  if [[ "$attempt" -eq 3 ]]; then
    exit 1
  fi
  echo "::warning::rustup install failed (attempt $attempt); clearing partial downloads and retrying."
  rm -f -- "$rustup_home"/downloads/*.partial
  sleep 5
done

if [[ "$toolchain" == "stable" ]]; then
  "$rustup" default stable
fi
echo "$cargo_bin" >> "${GITHUB_PATH:-/dev/null}"
"$rustup" run "$toolchain" rustc --version
