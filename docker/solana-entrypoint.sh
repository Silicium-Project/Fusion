#!/usr/bin/env bash
set -euo pipefail

if [[ $# -eq 0 ]]; then
  exec solana
fi

case "$1" in
  solana)
    shift
    exec solana "$@"
    ;;
  -*)
    exec solana "$@"
    ;;
  bash|sh|/bin/bash|/bin/sh)
    exec "$@"
    ;;
  *)
    if command -v "$1" >/dev/null 2>&1; then
      exec "$@"
    else
      exec solana "$@"
    fi
    ;;
esac
