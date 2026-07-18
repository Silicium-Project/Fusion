#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/opt/silicium}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/linux/install-vps.sh $ROOT" >&2
  exit 1
fi

apt-get update
apt-get install -y \
  ca-certificates \
  curl \
  git \
  nginx \
  docker.io \
  docker-compose-plugin \
  postgresql \
  postgresql-client \
  sqlite3 \
  openssl \
  python3 \
  python3-venv \
  python3-pip \
  golang-go

if ! command -v node >/dev/null 2>&1 || [[ "$(node -p 'Number(process.versions.node.split(".")[0])')" -lt 20 ]]; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
fi

mkdir -p /etc/silicium /var/lib/silicium/site /var/lib/silicium/network /var/lib/silicium/solana "$ROOT/bin"
systemctl enable --now docker

if [[ ! -d "$ROOT/.git" ]]; then
  echo "Expected repository cloned at $ROOT." >&2
  echo "Clone it first, or pass the existing repo path as first argument." >&2
  exit 1
fi

echo "Base VPS dependencies installed."
echo "Next:"
echo "  sudo cp deploy/env/*.example.env /etc/silicium/"
echo "  sudo bash deploy/linux/migrate-postgres-to-compose.sh $ROOT"
