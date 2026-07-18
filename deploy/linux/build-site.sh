#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/opt/silicium}"

install_js_dependencies() {
  if [[ -f package-lock.json || -f npm-shrinkwrap.json ]]; then
    if ! npm ci; then
      echo "npm ci could not use the lockfile; falling back to npm install."
      npm install
    fi
  else
    npm install
  fi
}

cd "$ROOT/FrontEnd"
install_js_dependencies
npm run build

cd "$ROOT/BackEnd"
go build -o "$ROOT/bin/silicium-backend" ./cmd

cd "$ROOT/Network/silicium-layer-dashboard"
install_js_dependencies
npm run build

cd "$ROOT/Network/solana-layer"
install_js_dependencies

echo "Silicium site build completed."
