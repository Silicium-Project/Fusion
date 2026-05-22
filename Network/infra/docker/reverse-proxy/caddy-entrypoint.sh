#!/bin/sh
set -euo pipefail

PROXY_SITE_ADDRESS="${PROXY_SITE_ADDRESS:-:443}"
PROXY_UPSTREAM_HOST="${PROXY_UPSTREAM_HOST:-silicium-localnet}"
PROXY_UPSTREAM_PORT="${PROXY_UPSTREAM_PORT:-8899}"
PROXY_TLS_MODE="${PROXY_TLS_MODE:-local}"
PROXY_TLS_EMAIL="${PROXY_TLS_EMAIL:-}"
PROXY_TLS_CERT_PATH="${PROXY_TLS_CERT_PATH:-/etc/caddy/certs/tls.crt}"
PROXY_TLS_KEY_PATH="${PROXY_TLS_KEY_PATH:-/etc/caddy/certs/tls.key}"

case "$PROXY_TLS_MODE" in
  acme)
    if [ -z "$PROXY_TLS_EMAIL" ]; then
      echo "PROXY_TLS_EMAIL must be set when PROXY_TLS_MODE=acme" >&2
      exit 1
    fi
    TLS_BLOCK="    tls $PROXY_TLS_EMAIL"
    ;;
  local)
    if [ ! -f "$PROXY_TLS_CERT_PATH" ] || [ ! -f "$PROXY_TLS_KEY_PATH" ]; then
      echo "TLS cert/key not found at $PROXY_TLS_CERT_PATH / $PROXY_TLS_KEY_PATH" >&2
      exit 1
    fi
    TLS_BLOCK="    tls $PROXY_TLS_CERT_PATH $PROXY_TLS_KEY_PATH"
    ;;
  internal)
    TLS_BLOCK="    tls internal"
    ;;
  *)
    echo "Unsupported PROXY_TLS_MODE='$PROXY_TLS_MODE'. Use acme, local or internal." >&2
    exit 1
    ;;
esac

mkdir -p /etc/caddy

{
  echo "{"
  if [ "$PROXY_TLS_MODE" = "acme" ]; then
    printf '    email %s
' "$PROXY_TLS_EMAIL"
  fi
  echo "}"

  printf '
%s {
' "$PROXY_SITE_ADDRESS"
  printf '%s

' "$TLS_BLOCK"
  cat <<EOF
    @healthz path /healthz
    handle @healthz {
        respond "ok" 200
    }

    reverse_proxy ${PROXY_UPSTREAM_HOST}:${PROXY_UPSTREAM_PORT}
}
EOF
} >/etc/caddy/Caddyfile

exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
