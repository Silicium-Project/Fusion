#!/usr/bin/env bash
# Read-only observation. Updates and account-link changes use the qualified delivery/API paths.
set -euo pipefail
case "${1:-status}" in
  status) exec sudo docker ps --filter 'name=silicium-dev-miniworker-' --format '{{.Names}} {{.Status}} {{.Image}}' ;;
  logs)
    worker="${2:-miniworker-01}"
    [[ "$worker" =~ ^miniworker-(0[1-9]|1[0-9]|2[0-4])$ ]] || { echo 'Expected miniworker-01..24' >&2; exit 2; }
    exec sudo docker logs --tail=80 "silicium-dev-$worker" ;;
  *) printf '%s\n' 'Runtime mutations require the qualified GitHub drain/canary procedure. Use status or logs miniworker-NN.' >&2; exit 2 ;;
esac
