#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"

cd "$ROOT"

if [[ ! -d "FrontEnd" || ! -d "BackEnd" || ! -d "apps/silicium-node" ]]; then
  echo "Expected FrontEnd, BackEnd and apps/silicium-node at $ROOT." >&2
  exit 1
fi

pushd FrontEnd >/dev/null
npm ci
npm test
npm run build
popd >/dev/null

pushd apps/silicium-node >/dev/null
npm ci
npm test
npm run build
popd >/dev/null

pushd BackEnd >/dev/null
go test ./...
popd >/dev/null
