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
  openssl \
  python3 \
  python3-venv \
  python3-pip \
  nodejs \
  npm \
  golang-go

mkdir -p /etc/silicium /var/lib/silicium/site /var/lib/silicium/network /var/lib/silicium/solana "$ROOT/bin"

if [[ ! -d "$ROOT/.git" ]]; then
  echo "Expected repository cloned at $ROOT." >&2
  echo "Clone it first, or pass the existing repo path as first argument." >&2
  exit 1
fi

echo "Base VPS dependencies installed."
echo "Next:"
echo "  sudo cp deploy/env/*.example.env /etc/silicium/"
echo "  sudo bash deploy/linux/build-site.sh $ROOT"
echo "  sudo bash deploy/linux/install-services.sh $ROOT"
