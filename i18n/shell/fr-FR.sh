#!/usr/bin/env bash

sil_i18n_catalog_lookup() {
  case "$1" in
    ci.e2e.build_demo) printf "%s" "Build et execution du demo splitter" ;;
    ci.e2e.worker_emu) printf "%s" "Execution worker (emu)" ;;
    ci.e2e.worker_native) printf "%s" "Execution worker (native)" ;;
    ci.e2e.build_dynamo) printf "%s" "Build de l'image dynamorio-runner" ;;
    ci.e2e.worker_dynamo) printf "%s" "Execution worker (dynamo)" ;;
    ci.e2e.proxy_smoke) printf "%s" "Smoke test proxy" ;;
    ci.e2e.warn_no_docker) printf "%s" "[WARN] Docker indisponible, etapes dynamo et proxy ignorees" ;;
    ci.e2e.python_tests) printf "%s" "Tests Python" ;;
    ci.e2e.ok) printf "%s" "Pipeline E2E OK" ;;
    ci.test_images.build_worker_builder) printf "%s" "Build worker builder" ;;
    ci.test_images.build_worker_runtime) printf "%s" "Build worker runtime" ;;
    ci.test_images.smoke_worker_runtime) printf "%s" "Smoke worker runtime (--help)" ;;
    ci.test_images.build_gui_runtime) printf "%s" "Build GUI runtime" ;;
    ci.test_images.smoke_gui_runtime) printf "%s" "Smoke GUI runtime en mode headless (--help)" ;;
    ci.test_images.build_gui_headless) printf "%s" "Build GUI headless runtime" ;;
    ci.test_images.smoke_gui_headless) printf "%s" "Smoke GUI headless (--help)" ;;
    ci.test_images.ok) printf "%s" "Tous les tests d'images Docker sont passes." ;;
    infra.secure.check_wireguard) printf "%s" "[secure-stack] Verification du module kernel WireGuard..." ;;
    infra.secure.warn_no_sudo) printf "%s" "Warning: sudo indisponible. Lancez ce script en root pour charger WireGuard." ;;
    infra.secure.warn_no_modprobe) printf "%s" "Warning: modprobe indisponible. Assurez-vous que le module WireGuard est charge." ;;
    infra.secure.pull_images) printf "%s" "[secure-stack] Pull des images..." ;;
    infra.secure.start_stack) printf "%s" "[secure-stack] Demarrage Solana RPC + hub WireGuard..." ;;
    infra.secure.active_services) printf "%s" "[secure-stack] Services actifs:" ;;
    infra.secure.peer_files) printf "%s" "Fichiers de configuration peers (partage securise avec calculateurs/verifyers):" ;;
    infra.secure.notes) cat <<'EOF'

Chaque fichier peer contient les cles privee/publique et les routes WireGuard.
Transmettez-le uniquement au noeud correspondant (calculator/verifier).

Une fois connecte via WireGuard, le worker peut joindre le RPC securise sur
l'adresse 10.42.0.2:8899. Exemple (depuis un worker):

  export SOLANA_URL=http://10.42.0.2:8899
  solana balance
  curl -s http://10.42.0.2:8899 -H 'Content-Type: application/json' \
    -d '{"jsonrpc":"2.0","id":1,"method":"getHealth"}'

Tous les paquets traversent le tunnel WireGuard (chiffrement ChaCha20-Poly1305).
EOF
      ;;
    infra.proxy.compose_not_found) printf "%s" "Fichier compose introuvable a %s" ;;
    infra.proxy.usage) cat <<'EOF'
Usage: infra/bin/run-with-proxy.sh [service-name]

Demarre le service Silicium demande avec le proxy TLS, genere automatiquement
un certificat autosigne quand PROXY_TLS_MODE=local (defaut), puis attend la
reponse de l'endpoint de health du proxy.

Variables d'environnement:
  PROXY_COMPOSE_PROFILES  Liste de profiles compose (separes par virgule)
                          (defaut "proxy").
  PROXY_UPSTREAM_HOST     Host du service cible (defaut nom du service).
  PROXY_UPSTREAM_PORT     Port RPC cible (defaut 8899).
  PROXY_TLS_MODE          local | acme | internal (defaut local).
  PROXY_TLS_EMAIL         Email requis en mode ACME.
  PROXY_TLS_CERT_PATH     Chemin cert TLS dans le container proxy
                          (defaut /etc/caddy/certs/tls.crt).
  PROXY_TLS_KEY_PATH      Chemin cle TLS dans le container proxy
                          (defaut /etc/caddy/certs/tls.key).
  PROXY_TLS_CERT_PATH_HOST  Chemin host cert genere (mode local).
  PROXY_TLS_KEY_PATH_HOST   Chemin host cle generee (mode local).
  PROXY_SITE_ADDRESS      Adresse servie par Caddy (defaut :443).
  PROXY_HTTP_PORT         Port host mappe vers le port 80 proxy (defaut 9080).
  PROXY_HTTPS_PORT        Port host mappe vers le port 443 proxy (defaut 9443).
  PROXY_TEST_URL          URL pour sonder le proxy (defaut https://localhost:9443/healthz, lie a PROXY_HTTPS_PORT).
  PROXY_SELF_SIGN_CN      Common Name cert autosigne (defaut rpc.local.silicium).
  PROXY_SELF_SIGN_DAYS    Duree de validite en jours (defaut 30).
EOF
      ;;
    infra.proxy.docker_missing) printf "%s" "CLI docker introuvable." ;;
    infra.proxy.openssl_missing) printf "%s" "CLI openssl introuvable (requis pour le mode TLS local)." ;;
    infra.proxy.gen_self_signed) printf "%s" "Generation certificat autosigne pour %s (%s jours)" ;;
    infra.proxy.start_service) printf "%s" "Demarrage de %s avec proxy (profiles: %s)" ;;
    infra.proxy.wait_health) printf "%s" "Attente du health proxy sur %s ..." ;;
    infra.proxy.up) printf "%s" "Proxy operationnel: %s" ;;
    infra.proxy.not_ready) printf "%s" "Le proxy n'a pas ete pret a temps. Verifiez les logs docker compose." ;;
    *) return 1 ;;
  esac
}
