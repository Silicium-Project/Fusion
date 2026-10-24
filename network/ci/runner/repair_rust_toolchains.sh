#!/usr/bin/env bash
# Remove rustup toolchains that can no longer run on this self-hosted runner.
#
# `anchor build` links a `solana` toolchain to the platform tools that
# cargo-build-sbf downloads into ~/.cache/solana/<version>/platform-tools.
# Two ways it breaks:
# - the cache is cleaned (disk reclaim): the link dangles and every tool that
#   lists the installed toolchains (Swatinem/rust-cache, rustup itself) fails
#   with "toolchain 'solana' is not installed";
# - the download is damaged (interrupted extraction): `cargo` or `rustc` lose
#   their execute bit and builds fail with "'cargo': Permission denied".
# A toolchain whose `rustc` or `cargo` cannot run is uninstalled; when it
# points into ~/.cache/solana, the damaged platform tools are deleted too, so
# that cargo-build-sbf downloads them again instead of relinking them.
set -euo pipefail

if ! command -v rustup >/dev/null 2>&1; then
  echo "rustup not found; nothing to repair."
  exit 0
fi

rustup_home="${RUSTUP_HOME:-$HOME/.rustup}"
solana_cache="$HOME/.cache/solana"

# Same lock as install_rust_toolchain.sh: a toolchain being installed by
# another job cannot run for a moment and must not be taken for broken.
mkdir -p "$rustup_home"
exec 9>"$rustup_home/.silicium-install.lock"
if ! flock -w 1800 9; then
  echo "::warning::Rust install lock busy; skipping the repair."
  exit 0
fi

# The platform-tools directory a toolchain links into, if it is in the
# Solana cache (nothing is deleted outside it).
solana_platform_tools() {
  local target
  target="$(readlink -f -- "$rustup_home/toolchains/$1" 2>/dev/null)" || return 1
  [[ "$target" == "$solana_cache"/*/platform-tools/* ]] || return 1
  echo "${target%/platform-tools/*}/platform-tools"
}

while read -r toolchain _; do
  [[ -n "$toolchain" ]] || continue
  if rustup run "$toolchain" rustc --version >/dev/null 2>&1 &&
    rustup run "$toolchain" cargo --version >/dev/null 2>&1; then
    continue
  fi
  # Only linked toolchains (Solana's) are removed: uninstalling `stable` or
  # a pinned version would take cargo away from every runner's builds.
  if [[ ! -L "$rustup_home/toolchains/$toolchain" ]]; then
    echo "::warning::Toolchain $toolchain does not run; reinstalling it."
    rustup toolchain install "$toolchain" --profile minimal --no-self-update --force || true
    continue
  fi
  echo "Removing broken toolchain: $toolchain"
  damaged="$(solana_platform_tools "$toolchain" || true)"
  rustup toolchain uninstall "$toolchain" || true
  if [[ -n "$damaged" && -d "$damaged" ]]; then
    echo "Removing damaged Solana platform tools: $damaged"
    rm -rf -- "$damaged"
  fi
done < <(rustup toolchain list 2>/dev/null | sed -e 's/ (.*)//')
