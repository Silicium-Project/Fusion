#!/usr/bin/env bash

sil_i18n_catalog_lookup() {
  case "$1" in
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
