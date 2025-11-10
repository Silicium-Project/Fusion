#!/usr/bin/env bash
set -euo pipefail

STACK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE="docker compose -f ${STACK_DIR}/docker-compose.yaml"

echo "[secure-stack] Checking WireGuard kernel module..."
if ! lsmod | grep -q "^wireguard"; then
  if command -v modprobe >/dev/null 2>&1; then
    sudo modprobe wireguard
  else
    echo "Warning: modprobe not available. Ensure the WireGuard kernel module is loaded." >&2
  fi
fi

echo "[secure-stack] Pulling images..."
${COMPOSE} pull

echo "[secure-stack] Starting Solana RPC + WireGuard hub..."
${COMPOSE} up -d

echo "[secure-stack] Active services:"
${COMPOSE} ps

echo
echo "Peer configuration files (share securely with calculateurs/vérificateurs) :"
find "${STACK_DIR}/wireguard/config" -maxdepth 1 -type d -name "peer-*" -print | while read -r dir; do
  conf="${dir}/peer.conf"
  [[ -f "$conf" ]] && echo "  - ${conf}"
done

cat <<'EOF'

Chaque fichier peer contient la clé privée/public et les routes WireGuard.
Transmettez-le uniquement au nœud correspondant (calculator/verifier).

Une fois connecté via WireGuard, le worker peut joindre le RPC sécurisé sur
l'adresse 10.42.0.2:8899. Exemple (depuis un worker) :

  export SOLANA_URL=http://10.42.0.2:8899
  solana balance
  curl -s http://10.42.0.2:8899 -H 'Content-Type: application/json' \
    -d '{"jsonrpc":"2.0","id":1,"method":"getHealth"}'

Tous les paquets traversent le tunnel WireGuard (chiffrement ChaCha20-Poly1305).
EOF
