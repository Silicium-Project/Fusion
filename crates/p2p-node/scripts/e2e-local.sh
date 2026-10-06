#!/usr/bin/env bash
# End-to-end check of the dev network shape, on loopback:
#   - an orchestrator (roles resource,storage, does not compute) publishes a
#     raytracer job, split into fragments;
#   - WORKERS desktop workers (default 1) start 5 s AFTER the publication,
#     on the dev channel, trusting the orchestrator only through the pinned
#     bootstrap address (/p2p/<peer id>).
# Passes when the orchestrator reassembles the image. With one worker, the
# worker verifies its own fragments (lone-worker rule); with two or more,
# each fragment is verified by another worker.
#
# Usage: crates/p2p-node/scripts/e2e-local.sh <scene.cfg> [out dir]
# Needs: cargo build --release -p p2p_node -p compute_daemon -p silicium-raytracer
# Ports used: 19092, 46201, 19100+n, 19200+n.
set -u
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
BIN="$ROOT/target/release"
SCENE=$(realpath "$1")
OUT=$(realpath -m "${2:-$ROOT/target/e2e-local}")
WORKERS=${WORKERS:-1}
rm -rf "$OUT"
mkdir -p "$OUT/o/work/scenes"
cp "$SCENE" "$OUT/o/work/scenes/scene.cfg"
pids=()
cleanup() { kill "${pids[@]}" 2>/dev/null; wait 2>/dev/null; }
trap cleanup EXIT

start_orchestrator() {
  (cd "$OUT/o" && env -i PATH="$PATH" HOME="$HOME" \
    SILICIUM_NODE_ID=orchestrator SILICIUM_NODE_ROLES=resource,storage \
    SILICIUM_RELEASE_CHANNEL=dev SILICIUM_DATA_DIR="$OUT/o" SILICIUM_COMPUTE_ROOT="$OUT/o/work" \
    API_PORT=19092 SILICIUM_P2P_BIND=127.0.0.1 SILICIUM_P2P_PORT=46201 \
    SILICIUM_ENABLE_QUIC_LISTENER=0 SILICIUM_WORK_OWN_TASKS=0 SILICIUM_MAX_FRAGMENTS=4 \
    "$BIN/p2p_node" >"$OUT/orchestrator.log" 2>&1) &
  pids+=($!)
}

# start_worker <n> <orchestrator peer id>
start_worker() {
  local n=$1 dir="$OUT/w$1"
  mkdir -p "$dir/work"
  (cd "$dir" && env -i PATH="$PATH" HOME="$HOME" \
    SILICIUM_COMPUTE_BIND="127.0.0.1:$((19100 + n))" SILICIUM_COMPUTE_ROOT="$dir/work" \
    SILICIUM_RAYTRACER_BIN="$BIN/silicium-raytracer" \
    "$BIN/compute_daemon" >"$dir/compute.log" 2>&1) &
  pids+=($!)
  (cd "$dir" && env -i PATH="$PATH" HOME="$HOME" \
    SILICIUM_NODE_ID="desktop$n" SILICIUM_NODE_ROLES=compute,verify \
    SILICIUM_RELEASE_CHANNEL=dev SILICIUM_DATA_DIR="$dir" SILICIUM_COMPUTE_ROOT="$dir/work" \
    API_PORT=$((19200 + n)) SILICIUM_P2P_BIND=127.0.0.1 SILICIUM_P2P_PORT=0 \
    SILICIUM_ENABLE_QUIC_LISTENER=0 \
    SILICIUM_BOOTSTRAP_PEERS="/ip4/127.0.0.1/tcp/46201/p2p/$2" \
    COMPUTE_DAEMON_URL="http://127.0.0.1:$((19100 + n))" \
    REPUTATION_BRIDGE_URL=http://127.0.0.1:1 \
    "$BIN/p2p_node" >"$dir/node.log" 2>&1) &
  pids+=($!)
}

start_orchestrator
for _ in $(seq 50); do grep -q "Local peer id" "$OUT/orchestrator.log" && break; sleep 0.2; done
ORCHESTRATOR=$(grep -o "Local peer id: [^ ]*" "$OUT/orchestrator.log" | awk '{print $4}')
sleep 1
curl -fsS -X POST localhost:19092/publish -H 'content-type: application/json' \
  -d '{"task_id":"e2ejob","scene_path":"scenes/scene.cfg","output_path":"out.ppm","seed":"42"}' >/dev/null
sleep 0.5
JOB=$(grep -o "Job [^ ]* split" "$OUT/orchestrator.log" | head -1 | awk '{print $2}')
echo "job $JOB published by $ORCHESTRATOR; workers join in 5 s"

sleep 5
for n in $(seq "$WORKERS"); do start_worker "$n" "$ORCHESTRATOR"; done

for second in $(seq 120); do
  sleep 1
  if [ -f "$OUT/o/work/results/$JOB.png" ]; then
    echo "OK: image reassembled after ${second}s ($OUT/o/work/results/$JOB.png)"
    for n in $(seq "$WORKERS"); do
      echo "worker $n: computed $(grep -c 'Compute successful' "$OUT/w$n/node.log")," \
        "verified $(grep -c 'Verdict on' "$OUT/w$n/node.log")"
    done
    exit 0
  fi
done
echo "FAIL: no reassembled image after 120 s (logs in $OUT)"
curl -s "localhost:19092/jobs/$JOB"; echo
exit 1
