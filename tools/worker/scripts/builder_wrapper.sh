#!/usr/bin/env bash
set -euo pipefail

if [[ $# -eq 0 ]]; then
    echo "Usage: $0 <command> [args...]" >&2
    exit 1
fi

# When already inside the GUI container (e.g. running in CI), run the command directly.
if [[ "${RUNNING_IN_GUI_CONTAINER:-}" == "1" ]]; then
    exec "$@"
fi

INVOCATION_DIR="$(pwd)"
if git rev-parse --show-toplevel >/dev/null 2>&1; then
    REPO_ROOT="$(git rev-parse --show-toplevel)"
else
    REPO_ROOT="${INVOCATION_DIR}"
fi

DOCKERFILE="${FRAGMENT_GUI_DOCKERFILE:-${REPO_ROOT}/tools/docker/gui-runner/Dockerfile}"
DOCKER_CONTEXT="${FRAGMENT_GUI_DOCKER_CONTEXT:-${REPO_ROOT}}"
IMAGE="${FRAGMENT_GUI_BUILDER_IMAGE:-luis1454/worker:1.0}"
TARGET="${FRAGMENT_GUI_DOCKER_TARGET:-builder}"

if ! docker image inspect "${IMAGE}" >/dev/null 2>&1; then
    docker build -t "${IMAGE}" -f "${DOCKERFILE}" --target "${TARGET}" "${DOCKER_CONTEXT}"
fi

# Align UID/GID so que les artefacts générés restent supprimables depuis l'hôte.
HOST_UID=$(id -u)
HOST_GID=$(id -g)

# Ajuste l'étiquette SELinux si nécessaire pour éviter les AVC (ex: Fedora).
VOLUME_SUFFIX=""
if [[ -d /sys/fs/selinux ]]; then
    VOLUME_SUFFIX=":z"
fi

RUN_CMD="$*"

exec docker run --rm \
    -e RUNNING_IN_GUI_CONTAINER=1 \
    -e RUN_CMD="${RUN_CMD}" \
    -e HOST_UID="${HOST_UID}" \
    -e HOST_GID="${HOST_GID}" \
    -v "${REPO_ROOT}:${REPO_ROOT}${VOLUME_SUFFIX}" \
    -w "${INVOCATION_DIR}" \
    --entrypoint /bin/bash \
    "${IMAGE}" -lc "apt-get update && apt-get install -y --no-install-recommends build-essential libjansson-dev pkg-config >/dev/null && bash -lc \"\$RUN_CMD\" && chown -R \${HOST_UID}:\${HOST_GID} ${INVOCATION_DIR}"
