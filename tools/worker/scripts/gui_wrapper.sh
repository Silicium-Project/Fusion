#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "Usage: gui_wrapper.sh <command> [args...]" >&2
    exit 1
fi

IMAGE="${FRAGMENT_GUI_DOCKER_IMAGE:-silicium/gui-runner:latest}"
if git rev-parse --show-toplevel >/dev/null 2>&1; then
    REPO_ROOT="$(git rev-parse --show-toplevel)"
else
    REPO_ROOT="$(pwd)"
fi
WORKDIR="$(pwd)"
DOCKERFILE="${FRAGMENT_GUI_DOCKERFILE:-${REPO_ROOT}/tools/docker/gui-runner/Dockerfile}"
DOCKER_CONTEXT="${FRAGMENT_GUI_DOCKER_CONTEXT:-${REPO_ROOT}}"

if ! docker image inspect "${IMAGE}" >/dev/null 2>&1; then
    echo "[gui-wrapper] Building image ${IMAGE}..."
    docker build -t "${IMAGE}" -f "${DOCKERFILE}" "${DOCKER_CONTEXT}"
fi

docker_args=(--rm --network host -e RUNNING_IN_GUI_CONTAINER=1)

if [[ -n "${FRAGMENT_GUI_VNC_PORT:-}" ]]; then
    docker_args+=(-e "VNC_PORT=${FRAGMENT_GUI_VNC_PORT}" "-p" "${FRAGMENT_GUI_VNC_PORT}:5900")
fi

docker_args+=(-v "${REPO_ROOT}:${REPO_ROOT}" -w "${WORKDIR}")

exec docker run "${docker_args[@]}" "${IMAGE}" "$@"
