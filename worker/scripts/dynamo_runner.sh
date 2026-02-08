#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "Usage: dynamo_runner.sh <binary> [args...]" >&2
    exit 1
fi


WORKSPACE="${WORKSPACE:-$(pwd -P)}"
IMAGE="${DYNAMO_RUNNER_IMAGE:-dynamorio-runner}"
SECURITY_MODE="${DYNAMO_RUNNER_SECURITY_MODE:-strict}"
DYNAMO_RUNNER_OPTS="${DYNAMO_RUNNER_OPTS:-}"
VOLUME_SPEC="${DYNAMO_RUNNER_VOLUME_SPEC:-/workspace:Z}"
DRRUN_FLAGS="${DYNAMO_RUNNER_DRRUN_FLAGS:--native_exec_managed_code}"
RUN_MODE="${DYNAMO_RUNNER_MODE:-native}"
DRRUN_BIN="${DYNAMO_RUNNER_DRRUN_BIN:-/opt/dynamorio/bin64/drrun}"
CONTAINER_DIR="${VOLUME_SPEC%%:*}"
if [[ -z "${CONTAINER_DIR}" ]]; then
    CONTAINER_DIR="/workspace"
fi
HOST_WORKSPACE="${HOST_WORKSPACE:-$WORKSPACE}"
RUN_USER="${DYNAMO_RUNNER_USER:-$(id -u):$(id -g)}"
RUN_NETWORK="${DYNAMO_RUNNER_NETWORK:-none}"
RUN_MEMORY="${DYNAMO_RUNNER_MEMORY:-2g}"
RUN_CPUS="${DYNAMO_RUNNER_CPUS:-2.0}"
RUN_PIDS="${DYNAMO_RUNNER_PIDS_LIMIT:-512}"
RUN_TMPFS_SIZE="${DYNAMO_RUNNER_TMPFS_SIZE:-64m}"

case "${SECURITY_MODE}" in
    strict|compat) ;;
    *)
        echo "[ERROR] DYNAMO_RUNNER_SECURITY_MODE must be 'strict' or 'compat' (got: ${SECURITY_MODE})" >&2
        exit 1
        ;;
esac

docker_run_base_args() {
    local args=(
        --rm
        -i
        --cap-drop ALL
        --cap-add SYS_PTRACE
        --security-opt no-new-privileges
        --user "${RUN_USER}"
        --network "${RUN_NETWORK}"
        --memory "${RUN_MEMORY}"
        --cpus "${RUN_CPUS}"
        --pids-limit "${RUN_PIDS}"
        --read-only
        --tmpfs "/tmp:rw,nosuid,nodev,noexec,size=${RUN_TMPFS_SIZE}"
        --tmpfs "/var/tmp:rw,nosuid,nodev,noexec,size=${RUN_TMPFS_SIZE}"
    )

    if [[ "${SECURITY_MODE}" == "compat" ]]; then
        args+=(--security-opt seccomp=unconfined --security-opt label=disable)
    fi

    if [[ -n "${DYNAMO_RUNNER_OPTS}" ]]; then
        local extra=()
        read -r -a extra <<< "${DYNAMO_RUNNER_OPTS}"
        args+=("${extra[@]}")
    fi

    printf '%s\0' "${args[@]}"
}

to_host_path() {
    local path="${1}"
    if [[ "${path}" == "${CONTAINER_DIR}"* ]]; then
        local rel="${path#"${CONTAINER_DIR}"}"
        printf '%s
' "${HOST_WORKSPACE}${rel}"
    else
        printf '%s
' "${path}"
    fi
}

to_container_path() {
    local path="${1}"
    if [[ "${path}" == "${CONTAINER_DIR}"* ]]; then
        printf '%s
' "${path}"
        return
    fi
    if [[ "${path}" == "${HOST_WORKSPACE}"* ]]; then
        local rel="${path#"${HOST_WORKSPACE}"}"
        printf '%s
' "${CONTAINER_DIR}${rel}"
    else
        printf '%s
' "${path}"
    fi
}

rewrite_payload_for_host() {
    local input_path="${1:-}"
    if [[ -z "${input_path}" || ! -f "${input_path}" ]]; then
        return
    fi
    python3 - "$input_path" "$CONTAINER_DIR" "$HOST_WORKSPACE" <<'PY'
import pathlib
import sys

input_file = pathlib.Path(sys.argv[1])
container_prefix = sys.argv[2]
host_prefix = sys.argv[3]
data = input_file.read_text()
if container_prefix != host_prefix:
    data = data.replace(container_prefix, host_prefix)
input_file.write_text(data)
PY
}

binary="$1"
shift

HOST_BINARY="$(to_host_path "${binary}")"
CONTAINER_BINARY="$(to_container_path "${HOST_BINARY}")"

if [[ ! -f "${HOST_BINARY}" ]]; then
    echo "[ERROR] Binaire runner introuvable: ${HOST_BINARY}" >&2
    exit 1
fi

orig_args=("$@")
host_args=()
container_args=()
i=0
while [[ $i -lt ${#orig_args[@]} ]]; do
    arg="${orig_args[$i]}"
    case "${arg}" in
        --input|--output)
            ((++i))
            if [[ $i -ge ${#orig_args[@]} ]]; then
                echo "Argument manquant pour ${arg}" >&2
                exit 1
            fi
            value="${orig_args[$i]}"
            host_value="$(to_host_path "${value}")"
            container_value="$(to_container_path "${host_value}")"
            host_args+=("${arg}" "${host_value}")
            container_args+=("${arg}" "${container_value}")
            ;;
        *)
            host_args+=("${arg}")
            container_args+=("${arg}")
            ;;
    esac
    ((++i))
done

should_use_docker=1
docker_error=""
if [[ "${DYNAMO_RUNNER_FORCE_HOST:-0}" == "1" ]]; then
    should_use_docker=0
elif ! command -v docker >/dev/null 2>&1; then
    docker_error="docker introuvable"
    should_use_docker=0
elif ! docker info >/dev/null 2>&1; then
    docker_error="docker non disponible (permissions ?)"
    should_use_docker=0
fi

if [[ "${should_use_docker}" -eq 0 ]]; then
    if [[ -n "${docker_error}" ]]; then
        echo "[WARN] ${docker_error} - exÃƒÂ©cution du runner sur l'hÃƒÂ´te" >&2
    fi
    host_input_path=""
    for (( idx=0; idx<${#host_args[@]}; ++idx )); do
        if [[ "${host_args[$idx]}" == "--input" && $((idx + 1)) -lt ${#host_args[@]} ]]; then
            host_input_path="${host_args[$((idx + 1))]}"
            break
        fi
    done
    if [[ -n "${host_input_path}" && ! -f "${host_input_path}" ]]; then
        echo "[ERROR] Fichier d'entrÃƒÂ©e manquant: ${host_input_path}" >&2
        exit 1
    fi
    rewrite_payload_for_host "${host_input_path}"
    exec "${HOST_BINARY}" "${host_args[@]}"
fi

if [[ "${RUN_MODE}" = "native" ]]; then
    mapfile -d '' -t docker_args < <(docker_run_base_args)
    docker run "${docker_args[@]}" \
        -v "${WORKSPACE}:${VOLUME_SPEC}" \
        -w "${CONTAINER_DIR}" \
        --entrypoint "${CONTAINER_BINARY}" \
        "${IMAGE}" "${container_args[@]}"
else
    if [[ -n "${DRRUN_FLAGS}" ]]; then
        IFS=' ' read -r -a DRRUN_ARGS <<< "${DRRUN_FLAGS}"
    else
        DRRUN_ARGS=()
    fi
    mapfile -d '' -t docker_args < <(docker_run_base_args)
    docker run "${docker_args[@]}" \
        -v "${WORKSPACE}:${VOLUME_SPEC}" \
        -w "${CONTAINER_DIR}" \
        --entrypoint "${DRRUN_BIN}" \
        "${IMAGE}" "${DRRUN_ARGS[@]}" -- \
        "${CONTAINER_BINARY}" "${container_args[@]}"
fi
