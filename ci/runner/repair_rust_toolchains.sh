#!/usr/bin/env bash
# Remove rustup toolchains that can no longer run on this self-hosted runner.
#
# `anchor build` links a `solana` toolchain to ~/.cache/solana/...; when that
# cache is cleaned (disk reclaim), the link dangles and every tool that lists
# the installed toolchains (Swatinem/rust-cache, rustup itself) fails with
# "toolchain 'solana' is not installed". A broken toolchain is useless, and the
# tool that needs it recreates it (cargo-build-sbf relinks `solana`), so it is
# safe to uninstall it here.
set -euo pipefail

if ! command -v rustup >/dev/null 2>&1; then
  echo "rustup not found; nothing to repair."
  exit 0
fi

while read -r toolchain _; do
  [[ -n "$toolchain" ]] || continue
  if ! rustup run "$toolchain" rustc --version >/dev/null 2>&1; then
    echo "Removing broken toolchain: $toolchain"
    rustup toolchain uninstall "$toolchain" || true
  fi
done < <(rustup toolchain list 2>/dev/null | sed -e 's/ (.*)//')
