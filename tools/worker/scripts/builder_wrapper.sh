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

IMAGE="${FRAGMENT_GUI_BUILDER_IMAGE:-luis1454/worker-builder:1.0}"

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
    --user "${HOST_UID}:${HOST_GID}" \
    -e RUNNING_IN_GUI_CONTAINER=1 \
    -v "${REPO_ROOT}:${REPO_ROOT}${VOLUME_SUFFIX}" \
    -w "${INVOCATION_DIR}" \
    --entrypoint /bin/bash \
    "${IMAGE}" -lc "${RUN_CMD}"
