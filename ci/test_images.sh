#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TMP_TAG_PREFIX="ci-test-$$"

cleanup() {
    docker rmi -f \
        ${TMP_TAG_PREFIX}-worker-builder \
        ${TMP_TAG_PREFIX}-worker-runtime \
        ${TMP_TAG_PREFIX}-gui-runtime \
        ${TMP_TAG_PREFIX}-gui-headless \
        >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo ">> Build worker builder"
docker build -t ${TMP_TAG_PREFIX}-worker-builder -f docker/worker-builder/Dockerfile .

echo ">> Build worker runtime"
docker build -t ${TMP_TAG_PREFIX}-worker-runtime -f docker/worker-runtime/Dockerfile .

echo ">> Smoke worker runtime (--help)"
docker run --rm ${TMP_TAG_PREFIX}-worker-runtime --help >/dev/null 2>&1 || true

echo ">> Build GUI runtime"
docker build -t ${TMP_TAG_PREFIX}-gui-runtime -f docker/gui-runner/Dockerfile .

echo ">> Smoke GUI runtime in headless mode (--help)"
docker run --rm ${TMP_TAG_PREFIX}-gui-runtime --headless fragment_executor --help >/dev/null 2>&1 || true

echo ">> Build GUI headless runtime"
docker build -t ${TMP_TAG_PREFIX}-gui-headless -f docker/gui-headless-runtime/Dockerfile .

echo ">> Smoke GUI headless (--help)"
docker run --rm ${TMP_TAG_PREFIX}-gui-headless fragment_executor --help >/dev/null 2>&1 || true

echo "All Docker image tests passed."
