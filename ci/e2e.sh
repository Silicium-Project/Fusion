#!/usr/bin/env bash
# End-to-end check of the Rust network, on loopback, without Docker: builds
# the release binaries, then runs crates/p2p-node/scripts/e2e-local.sh for
#   - a raytracer job with one worker (lone-worker self-verification),
#   - the same job with two workers (cross-verification),
#   - a calcul/integrity/sha256 job (result checked against hashlib).
# Replaces the Docker e2e of the former Python network (docker_e2e.sh).
#
# Usage: ci/e2e.sh [out dir]   (default target/e2e)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$(realpath -m "${1:-$ROOT/target/e2e}")"
SCENE="$ROOT/crates/raytracer/scenes/silicium-multi-fragment-scene.cfg"
RUN="$ROOT/crates/p2p-node/scripts/e2e-local.sh"
cd "$ROOT"

echo ">> Building p2p_node, compute_daemon and silicium-raytracer (release)"
cargo build --release --locked -p p2p_node -p compute_daemon -p silicium-raytracer

echo ">> Raytracer, one worker"
WORKERS=1 bash "$RUN" "$SCENE" "$OUT/raytracer-1"
echo ">> Raytracer, two workers"
WORKERS=2 bash "$RUN" "$SCENE" "$OUT/raytracer-2"
echo ">> sha256, one worker"
WORKLOAD=calcul/integrity/sha256 WORKERS=1 bash "$RUN" "$SCENE" "$OUT/sha256"

echo ">> End-to-end OK"
