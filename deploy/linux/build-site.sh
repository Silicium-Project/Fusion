#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/opt/silicium}"

cd "$ROOT/Site/FrontEnd-main"
npm ci
npm run build

cd "$ROOT/Site/BackEnd-main"
go build -o "$ROOT/bin/silicium-backend" ./cmd

cd "$ROOT/Network/silicium-layer-dashboard"
npm ci
npm run build

cd "$ROOT/Network/solana-layer"
npm ci

echo "Silicium site build completed."
