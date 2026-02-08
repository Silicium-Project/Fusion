#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# shellcheck source=infra/bin/i18n.sh
. "$ROOT/infra/bin/i18n.sh"

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

echo ">> $(sil_i18n_lookup "ci.test_images.build_worker_builder")"
docker build -t ${TMP_TAG_PREFIX}-worker-builder -f docker/worker-builder/Dockerfile .

echo ">> $(sil_i18n_lookup "ci.test_images.build_worker_runtime")"
docker build -t ${TMP_TAG_PREFIX}-worker-runtime -f docker/worker-runtime/Dockerfile .

echo ">> $(sil_i18n_lookup "ci.test_images.smoke_worker_runtime")"
docker run --rm ${TMP_TAG_PREFIX}-worker-runtime --help >/dev/null 2>&1 || true

echo ">> $(sil_i18n_lookup "ci.test_images.build_gui_runtime")"
docker build -t ${TMP_TAG_PREFIX}-gui-runtime -f docker/gui-runner/Dockerfile .

echo ">> $(sil_i18n_lookup "ci.test_images.smoke_gui_runtime")"
docker run --rm ${TMP_TAG_PREFIX}-gui-runtime --headless fragment_executor --help >/dev/null 2>&1 || true

echo ">> $(sil_i18n_lookup "ci.test_images.build_gui_headless")"
docker build -t ${TMP_TAG_PREFIX}-gui-headless -f docker/gui-headless-runtime/Dockerfile .

echo ">> $(sil_i18n_lookup "ci.test_images.smoke_gui_headless")"
docker run --rm ${TMP_TAG_PREFIX}-gui-headless fragment_executor --help >/dev/null 2>&1 || true

sil_i18n_echo "ci.test_images.ok"
