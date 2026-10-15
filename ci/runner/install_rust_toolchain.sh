#!/usr/bin/env bash
# Install (or update) a rustup toolchain on a self-hosted runner, one job at a time.
#
# Usage: install_rust_toolchain.sh <toolchain> [component,...]
#
# The runners on the VPS share one ~/.rustup. When a new stable Rust is
# released, every job starting at that moment updates the same toolchain and
# they break each other's downloads ("could not rename 'downloaded' file ...
# .partial"). This takes an exclusive lock on the rustup home (waits up to
# 30 min), installs, retries twice on a failed download, and sets `stable` as
# the default toolchain like dtolnay/rust-toolchain did.
#
# A toolchain that is already installed and runs is NOT updated (set
# SILICIUM_RUST_UPDATE=1 to update it): on a Rust release day, updating
# `stable` replaced cargo and rustc under the builds of the other runners,
# which failed with "could not parse/generate dep info" and "'cargo' is
# missing from PATH". Builds hold this lock shared (retry_on_corruption.sh),
# so an update waits for them to finish.
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
if ! flock -w 1800 9; then
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

# Components asked for that the installed toolchain does not have yet.
missing_components() {
  local installed component
  installed="$("$rustup" component list --installed --toolchain "$toolchain" 2>/dev/null)" || return 0
  IFS=',' read -ra wanted <<<"$components"
  for component in "${wanted[@]}"; do
    [[ -z "$component" ]] || grep -q "^$component" <<<"$installed" || echo "$component"
  done
}

already_installed=false
if [[ "${SILICIUM_RUST_UPDATE:-0}" != 1 ]] &&
  "$rustup" run "$toolchain" rustc --version >/dev/null 2>&1 &&
  "$rustup" run "$toolchain" cargo --version >/dev/null 2>&1 &&
  [[ -z "$(missing_components)" ]]; then
  echo "Rust $toolchain is already installed; not updating it (SILICIUM_RUST_UPDATE=1 to update)."
  already_installed=true
fi

for attempt in 1 2 3; do
  if "$already_installed" || "$rustup" "${args[@]}"; then
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

# Put the directory that really holds `cargo` on the PATH of the next steps.
# It is $cargo_bin for a rustup installed by rustup-init; a rustup found
# elsewhere (a distribution package, another account's PATH) keeps its
# proxies in another directory, and `cargo` would then be missing.
cargo_dir="$cargo_bin"
if [[ ! -x "$cargo_dir/cargo" ]]; then
  if [[ -x "$(dirname "$rustup")/cargo" ]]; then
    cargo_dir="$(dirname "$rustup")"
  else
    cargo_dir="$(dirname "$("$rustup" which --toolchain "$toolchain" cargo)")"
  fi
  echo "::notice::cargo is not in $cargo_bin for $(id -un); using $cargo_dir."
fi
if ! PATH="$cargo_dir:$PATH" cargo --version >/dev/null 2>&1; then
  echo "::error::cargo cannot run from $cargo_dir for $(id -un) (HOME=$HOME)." >&2
  exit 1
fi
echo "$cargo_dir" >> "${GITHUB_PATH:-/dev/null}"
"$rustup" run "$toolchain" rustc --version
