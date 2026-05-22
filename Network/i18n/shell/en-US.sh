#!/usr/bin/env bash

sil_i18n_catalog_lookup() {
  case "$1" in
    ci.e2e.build_demo) printf "%s" "Build and run splitter demo" ;;
    ci.e2e.worker_emu) printf "%s" "Worker run (emu)" ;;
    ci.e2e.worker_native) printf "%s" "Worker run (native)" ;;
    ci.e2e.build_dynamo) printf "%s" "Building dynamorio-runner image" ;;
    ci.e2e.worker_dynamo) printf "%s" "Worker run (dynamo)" ;;
    ci.e2e.proxy_smoke) printf "%s" "Proxy smoke test" ;;
    ci.e2e.warn_no_docker) printf "%s" "[WARN] Docker unavailable, dynamo and proxy steps skipped" ;;
    ci.e2e.python_tests) printf "%s" "Python tests" ;;
    ci.e2e.ok) printf "%s" "E2E pipeline OK" ;;
    ci.test_images.build_worker_builder) printf "%s" "Build worker builder" ;;
    ci.test_images.build_worker_runtime) printf "%s" "Build worker runtime" ;;
    ci.test_images.smoke_worker_runtime) printf "%s" "Smoke worker runtime (--help)" ;;
    ci.test_images.build_gui_runtime) printf "%s" "Build GUI runtime" ;;
    ci.test_images.smoke_gui_runtime) printf "%s" "Smoke GUI runtime in headless mode (--help)" ;;
    ci.test_images.build_gui_headless) printf "%s" "Build GUI headless runtime" ;;
    ci.test_images.smoke_gui_headless) printf "%s" "Smoke GUI headless (--help)" ;;
    ci.test_images.ok) printf "%s" "All Docker image tests passed." ;;
    infra.secure.check_wireguard) printf "%s" "[secure-stack] Checking WireGuard kernel module..." ;;
    infra.secure.warn_no_sudo) printf "%s" "Warning: sudo not available. Run this script as root to load WireGuard." ;;
    infra.secure.warn_no_modprobe) printf "%s" "Warning: modprobe not available. Ensure the WireGuard kernel module is loaded." ;;
    infra.secure.pull_images) printf "%s" "[secure-stack] Pulling images..." ;;
    infra.secure.start_stack) printf "%s" "[secure-stack] Starting Solana RPC + WireGuard hub..." ;;
    infra.secure.active_services) printf "%s" "[secure-stack] Active services:" ;;
    infra.secure.peer_files) printf "%s" "Peer configuration files (share securely with calculators/verifiers):" ;;
    infra.secure.notes) cat <<'EOF'

Each peer file contains private/public keys and WireGuard routes.
Share it only with the corresponding node (calculator/verifier).

Once connected over WireGuard, the worker can reach the secure RPC at
10.42.0.2:8899. Example (from a worker):

  export SOLANA_URL=http://10.42.0.2:8899
  solana balance
  curl -s http://10.42.0.2:8899 -H 'Content-Type: application/json' \
    -d '{"jsonrpc":"2.0","id":1,"method":"getHealth"}'

All packets traverse the WireGuard tunnel (ChaCha20-Poly1305 encryption).
EOF
      ;;
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
