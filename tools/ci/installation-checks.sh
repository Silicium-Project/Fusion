#!/usr/bin/env bash
set -euo pipefail
root="$(git rev-parse --show-toplevel)"
snapshot="$root/.artifacts/snapshot"
[[ -s "$snapshot/snapshot.json" ]] || { echo 'Missing complete package snapshot' >&2; exit 1; }
# Test the published snippets against the immutable repository, not a local package path.
network="silicium-install-${GITHUB_RUN_ID:?}"
docker network create "$network" >/dev/null
cleanup() { docker rm -f "${network}-http" >/dev/null 2>&1 || true; docker network rm "$network" >/dev/null 2>&1 || true; }
trap cleanup EXIT
docker run -d --rm --name "${network}-http" --network "$network" -v "$snapshot:/usr/share/nginx/html:ro" nginx:1.27-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10 >/dev/null
base="http://${network}-http"
suite=stable
[[ "${RELEASE_CHANNEL:?}" == dev ]] && suite=dev
for image in debian:12@sha256:854dd8ab51d62866dbd8f5431d15ce77b12983a2a4a1e1fe43a2395dc7ef9f61 ubuntu:24.04@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac; do
  docker run --rm --network "$network" -e BASE="$base" -e SUITE="$suite" "$image" bash -euc '
    apt-get update -qq; apt-get install -y --no-install-recommends curl gnupg ca-certificates
    install -d /etc/apt/keyrings
    curl -fsSL "$BASE/apt/silicium-packages.asc" | gpg --dearmor > /etc/apt/keyrings/silicium.gpg
    printf "Types: deb\nURIs: %s/apt\nSuites: %s\nComponents: main\nArchitectures: amd64\nSigned-By: /etc/apt/keyrings/silicium.gpg\n" "$BASE" "$SUITE" > /etc/apt/sources.list.d/silicium.sources
    apt-get update -qq; apt-get install -y silicium-node
    dpkg-query -W silicium-node; test -x /usr/bin/silicium-node
    apt-get install -y silicium-node; dpkg --verify silicium-node
  '
done
docker run --rm --network "$network" -e BASE="$base" fedora:44@sha256:43b29f65a41eb9c35e1cd5323e3bdf3b655c2357a9f4f1ff2f9c2798e5045d80 bash -euc '
  dnf install -y curl ca-certificates
  curl -fsSL "$BASE/rpm/silicium-node.repo" | sed "s#https://.*/snapshots/[^/]*/rpm#$BASE/rpm#g" > /etc/yum.repos.d/silicium.repo
  dnf makecache --repo="silicium-*"; dnf install -y silicium-node
  rpm -q silicium-node; test -x /usr/bin/silicium-node; rpm -V silicium-node
  dnf reinstall -y silicium-node
'
