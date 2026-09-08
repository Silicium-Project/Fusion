#!/usr/bin/env bash

sil_i18n_catalog_lookup() {
  case "$1" in
   infra.proxy.compose_not_found) printf "%s" "Compose file not found at %s" ;;
    infra.proxy.usage) cat <<'EOF'
Usage: infra/bin/run-with-proxy.sh [service-name]

Starts the requested Silicium service together with the TLS proxy, auto-generates
a self-signed certificate when PROXY_TLS_MODE=local (default), and waits until the
proxy health endpoint answers.

Environment variables:
  PROXY_COMPOSE_PROFILES  Comma-separated list of compose profiles to enable
                          (defaults to "proxy").
  PROXY_UPSTREAM_HOST     Target service host (defaults to the service name).
  PROXY_UPSTREAM_PORT     Target RPC port (default 8899).
  PROXY_TLS_MODE          local | acme | internal (default local).
  PROXY_TLS_EMAIL         Email required for ACME mode.
  PROXY_TLS_CERT_PATH     Path to TLS certificate inside the proxy container
                          (default /etc/caddy/certs/tls.crt).
  PROXY_TLS_KEY_PATH      Path to TLS key inside the proxy container
                          (default /etc/caddy/certs/tls.key).
  PROXY_TLS_CERT_PATH_HOST  Host path for generated TLS certificate (local mode).
  PROXY_TLS_KEY_PATH_HOST   Host path for generated TLS key (local mode).
  PROXY_SITE_ADDRESS      Address served by Caddy (default :443).
  PROXY_HTTP_PORT         Host port mapped to the proxy's port 80 (default 9080).
  PROXY_HTTPS_PORT        Host port mapped to the proxy's port 443 (default 9443).
  PROXY_TEST_URL          URL used to probe the proxy (default https://localhost:9443/healthz, tied to PROXY_HTTPS_PORT).
  PROXY_SELF_SIGN_CN      Common Name for self-signed certs (default rpc.local.silicium).
  PROXY_SELF_SIGN_DAYS    Validity in days for generated certs (default 30).
EOF
      ;;
    infra.proxy.docker_missing) printf "%s" "docker CLI not found." ;;
    infra.proxy.openssl_missing) printf "%s" "openssl CLI not found (required for local TLS mode)." ;;
    infra.proxy.gen_self_signed) printf "%s" "Generating self-signed certificate for %s (%s days)" ;;
    infra.proxy.start_service) printf "%s" "Starting %s with proxy (profiles: %s)" ;;
    infra.proxy.wait_health) printf "%s" "Waiting for proxy health at %s ..." ;;
    infra.proxy.up) printf "%s" "Proxy is up: %s" ;;
    infra.proxy.not_ready) printf "%s" "Proxy did not become ready in time. Check docker compose logs." ;;
    *) return 1 ;;
  esac
}
