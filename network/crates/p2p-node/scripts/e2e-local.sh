#!/usr/bin/env bash
# End-to-end check of the dev network shape, on loopback:
#   - an orchestrator (roles resource,storage, does not compute) publishes a
#     raytracer job, split into fragments;
#   - WORKERS desktop workers (default 1) join on the dev channel, trusting
#     the orchestrator only through the pinned bootstrap address
#     (/p2p/<peer id>); set WORKERS_BEFORE_PUBLISH=1 to form the mesh first.
# Passes when the orchestrator assembles the job result. With one worker,
# the worker verifies its own fragments (lone-worker rule); with two or more,
# each fragment is verified by another worker.
#
# WORKLOAD selects the workload (default `raytracer`, input = a scene;
# `calcul/integrity/sha256`, input = any file, checked against Python's
# hashlib; `ai/embedding/test-tiny`, input = documents (.txt, .md, .pdf,
# .docx or .zip), checked by a search through the control API; or
# `ai/llm/test-tiny`, input = a `silicium-llm-request/1` JSON file, answered
# by a fake Ollama per worker, checked item by item).
#
# Usage: crates/p2p-node/scripts/e2e-local.sh <input file> [out dir]
# Needs: cargo build --release -p p2p_node -p compute_daemon -p silicium-raytracer
#        (with `--features p2p_node/test-model` for ai/embedding/test-tiny;
#        with `--features p2p_node/test-ollama -p silicium-llm --features
#        silicium-llm/test-ollama` for ai/llm/test-tiny)
# Ports: API 19092, libp2p 46201, workers 19100+n and 19200+n, all shifted by
# E2E_PORT_OFFSET (default 0) so that parallel runs on one host do not collide.
set -u
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
BIN="$ROOT/target/release"
SCENE=$(realpath "$1")
OUT=$(realpath -m "${2:-$ROOT/target/e2e-local}")
WORKERS=${WORKERS:-1}
WORKLOAD=${WORKLOAD:-raytracer}
OFFSET=${E2E_PORT_OFFSET:-0}
JOB_TIMEOUT_SECS=${E2E_JOB_TIMEOUT_SECS:-240}
WORKERS_BEFORE_PUBLISH=${WORKERS_BEFORE_PUBLISH:-0}
REQUIRE_DELEGATION=${REQUIRE_DELEGATION:-0}
REQUIRE_DHT_CAPACITY=${REQUIRE_DHT_CAPACITY:-0}
API=$((19092 + OFFSET))
P2P=$((46201 + OFFSET))
COMPUTE_BASE=$((19100 + OFFSET))
WORKER_API_BASE=$((19200 + OFFSET))
OLLAMA_BASE=$((19300 + OFFSET))
case "$WORKLOAD" in
  raytracer) FINAL_EXTENSION=png ;;
  ai/embedding/*) FINAL_EXTENSION=index.json ;;
  ai/llm/*) FINAL_EXTENSION=result.json ;;
  *) FINAL_EXTENSION=json ;;
esac
# The input keeps its name: document search reads the format from it.
INPUT_NAME=$(basename "$SCENE")
rm -rf "$OUT"
mkdir -p "$OUT/o/work/scenes"
cp "$SCENE" "$OUT/o/work/scenes/$INPUT_NAME"
pids=()
cleanup() { kill "${pids[@]}" 2>/dev/null; wait 2>/dev/null; }
trap cleanup EXIT

start_orchestrator() {
  (cd "$OUT/o" && exec env -i PATH="$PATH" HOME="$HOME" \
    SILICIUM_NODE_ID=orchestrator SILICIUM_NODE_ROLES=resource,storage \
    SILICIUM_ENABLE_MDNS=0 \
    SILICIUM_RELEASE_CHANNEL=dev SILICIUM_DATA_DIR="$OUT/o" SILICIUM_COMPUTE_ROOT="$OUT/o/work" \
    API_PORT=$API SILICIUM_P2P_BIND=127.0.0.1 SILICIUM_P2P_PORT=$P2P \
    SILICIUM_ENABLE_QUIC_LISTENER=0 SILICIUM_WORK_OWN_TASKS=0 SILICIUM_MAX_FRAGMENTS=4 \
    SILICIUM_EMBEDDING_PASSAGES_PER_FRAGMENT="${PASSAGES_PER_FRAGMENT:-8}" \
    SILICIUM_LLM_ITEMS_PER_FRAGMENT="${ITEMS_PER_FRAGMENT:-4}" \
    SILICIUM_TARGET_BYTES_PER_FRAGMENT="${TARGET_BYTES:-4194304}" \
    "$BIN/p2p_node" >"$OUT/orchestrator.log" 2>&1) &
  pids+=($!)
}

# start_worker <n> <orchestrator peer id>
start_worker() {
  local n=$1 dir="$OUT/w$1" ollama=()
  mkdir -p "$dir/work"
  if [[ "$WORKLOAD" == ai/llm/* ]]; then
    "$BIN/silicium-llm" fake-ollama --bind "127.0.0.1:$((OLLAMA_BASE + n))" >"$dir/ollama.log" 2>&1 &
    pids+=($!)
    ollama=(SILICIUM_OLLAMA_URL="http://127.0.0.1:$((OLLAMA_BASE + n))")
  fi
  (cd "$dir" && exec env -i PATH="$PATH" HOME="$HOME" \
    SILICIUM_COMPUTE_BIND="127.0.0.1:$((COMPUTE_BASE + n))" SILICIUM_COMPUTE_ROOT="$dir/work" \
    SILICIUM_RAYTRACER_BIN="$BIN/silicium-raytracer" \
    "$BIN/compute_daemon" >"$dir/compute.log" 2>&1) &
  pids+=($!)
  (cd "$dir" && exec env -i PATH="$PATH" HOME="$HOME" \
    SILICIUM_NODE_ID="desktop$n" SILICIUM_NODE_ROLES=compute,verify \
    SILICIUM_ENABLE_MDNS=0 \
    SILICIUM_RELEASE_CHANNEL=dev SILICIUM_DATA_DIR="$dir" SILICIUM_COMPUTE_ROOT="$dir/work" \
    SILICIUM_EXPORT_DIR="$dir/export" API_PORT=$((WORKER_API_BASE + n)) SILICIUM_P2P_BIND=127.0.0.1 SILICIUM_P2P_PORT=0 \
    SILICIUM_ENABLE_QUIC_LISTENER=0 \
    SILICIUM_BOOTSTRAP_PEERS="/ip4/127.0.0.1/tcp/$P2P/p2p/$2" \
    COMPUTE_DAEMON_URL="http://127.0.0.1:$((COMPUTE_BASE + n))" \
    REPUTATION_BRIDGE_URL=http://127.0.0.1:1 "${ollama[@]}" \
    "$BIN/p2p_node" >"$dir/node.log" 2>&1) &
  pids+=($!)
}

start_orchestrator
for _ in $(seq 50); do grep -q "Local peer id" "$OUT/orchestrator.log" && break; sleep 0.2; done
ORCHESTRATOR=$(grep -o "Local peer id: [^ ]*" "$OUT/orchestrator.log" | awk '{print $4}')
# The API listens a moment after the identity is printed (later on a busy CI
# runner): wait for it, and stop with the log if it never comes up.
api_ready() { curl -fsS --max-time 2 "http://127.0.0.1:$API/healthz" >/dev/null 2>&1; }
deadline=$((SECONDS + 30))
until api_ready; do
  if ! kill -0 "${pids[0]}" 2>/dev/null; then
    echo "FAIL: the orchestrator stopped (a port in use? API $API, libp2p $P2P)"
    tail -n 40 "$OUT/orchestrator.log"
    exit 1
  fi
  if (( SECONDS >= deadline )); then
    echo "FAIL: the orchestrator API is not answering on 127.0.0.1:$API after 30 s"
    tail -n 40 "$OUT/orchestrator.log"
    exit 1
  fi
  sleep 0.2
done
if [[ "$WORKERS_BEFORE_PUBLISH" == 1 ]]; then
  for n in $(seq "$WORKERS"); do start_worker "$n" "$ORCHESTRATOR"; done
  echo "workers started; waiting for signed compute profiles to cross the gossip mesh"
  mesh_deadline=$((SECONDS + 60))
  mesh_ready=0
  while (( SECONDS < mesh_deadline )); do
    if python3 - "$WORKERS" "$WORKER_API_BASE" <<'PY'
import json, sys, urllib.request
workers, base = map(int, sys.argv[1:])
for worker in range(1, workers + 1):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{base + worker}/v1/peers", timeout=2) as response:
            peers = json.load(response)["peers"]
    except Exception:
        raise SystemExit(1)
    online_workers = [
        peer for peer in peers
        if peer.get("online") and peer.get("profile_known") and not peer.get("self")
        and peer.get("task_author")
        and any(role.strip().lower() == "compute" for role in peer.get("roles", []))
    ]
    if len(online_workers) < workers - 1:
        raise SystemExit(1)
PY
    then
      mesh_ready=1
      break
    fi
    sleep 1
  done
  if (( mesh_ready == 0 )); then
    echo "FAIL: workers did not see all other compute profiles through gossip within 60 s"
    for n in $(seq "$WORKERS"); do
      echo "--- worker $n peer view"
      curl -s --max-time 3 "http://127.0.0.1:$((WORKER_API_BASE + n))/v1/peers" || true
      echo
      echo "--- worker $n log"
      tail -n 30 "$OUT/w$n/node.log"
    done
    exit 1
  fi
  echo "mesh ready: every worker sees $((WORKERS - 1)) other compute worker(s); publishing job"
else
  echo "job will be published before the workers join"
fi

curl -fsS --max-time 10 -X POST "http://127.0.0.1:$API/publish" -H 'content-type: application/json' \
  -d '{"task_id":"e2ejob","scene_path":"scenes/'"$INPUT_NAME"'","output_path":"out","seed":"42","workload":"'"$WORKLOAD"'"}' >/dev/null \
  || { echo "FAIL: the orchestrator refused the job"; tail -n 40 "$OUT/orchestrator.log"; exit 1; }
sleep 0.5
JOB=$(grep -o "Job [^ ]* split" "$OUT/orchestrator.log" | head -1 | awk '{print $2}')
if [[ "$WORKERS_BEFORE_PUBLISH" == 1 ]]; then
  echo "job $JOB published by $ORCHESTRATOR to the formed worker mesh"
else
  echo "job $JOB published by $ORCHESTRATOR; workers join in 5 s"
  sleep 5
  for n in $(seq "$WORKERS"); do start_worker "$n" "$ORCHESTRATOR"; done
fi

for second in $(seq "$JOB_TIMEOUT_SECS"); do
  sleep 1
  if [ -f "$OUT/o/work/results/$JOB.$FINAL_EXTENSION" ]; then
    echo "OK: $WORKLOAD job assembled after ${second}s ($OUT/o/work/results/$JOB.$FINAL_EXTENSION)"
    if [[ "$WORKLOAD" == ai/embedding/* ]]; then
      sleep 1
      curl -fsS --max-time 30 -X POST "http://127.0.0.1:$API/v1/embedding/search" -H 'content-type: application/json' \
        -d '{"jobs":["'"$JOB"'"],"query":"'"${QUERY:-contrat}"'","top_k":3}' >"$OUT/search.json" || exit 1
      python3 - "$OUT/search.json" "$OUT/o/work/results/$JOB.index.json" <<'PY' || exit 1
import json, sys
hits = json.load(open(sys.argv[1]))["hits"]
index = json.load(open(sys.argv[2]))
assert hits and all(h["score"] >= hits[-1]["score"] for h in hits), hits
print(f"search: {index['passage_count']} passages of {len(index['documents'])} document(s), best: {hits[0]['document']} p.{hits[0]['page']} ({hits[0]['score']:.3f})")
PY
    elif [[ "$WORKLOAD" == ai/llm/* ]]; then
      python3 - "$OUT/o/work/results/$JOB.answers.jsonl" "$OUT/o/work/results/$JOB.result.json" "$SCENE" <<'PY' || exit 1
import json, sys
answers = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8")]
result = json.load(open(sys.argv[2], encoding="utf-8"))
request = json.load(open(sys.argv[3], encoding="utf-8"))
assert [a["id"] for a in answers] == list(range(len(request["items"]))), "every item, in order"
assert [a["input"] for a in answers] == [item.strip() for item in request["items"]]
assert all(a["output"] not in (None, "") for a in answers), answers
assert result["item_count"] == len(answers) and result["answered"] == len(answers)
print(f"llm: {len(answers)} items answered, first: {answers[0]['output']!r}")
PY
    elif [[ "$WORKLOAD" != raytracer ]]; then
      python3 - "$OUT/o/work/results/$JOB.json" "$SCENE" <<'PY' || exit 1
import hashlib, json, sys
result = json.load(open(sys.argv[1]))
data = open(sys.argv[2], "rb").read()
chunks = result["chunks"]
assert result["size_bytes"] == len(data) and chunks[-1]["offset"] + chunks[-1]["length"] == len(data)
for chunk in chunks:
    piece = data[chunk["offset"]:chunk["offset"] + chunk["length"]]
    assert chunk["sha256"] == hashlib.sha256(piece).hexdigest(), chunk
print(f"sha256: {len(chunks)} chunk(s) match hashlib")
PY
    fi
    for n in $(seq "$WORKERS"); do
      journal="$OUT/w$n/export/node.events.ndjson"
      delegated=$(grep -c 'Delegated .* into .* child tasks' "$OUT/w$n/node.log" 2>/dev/null || true)
      echo "worker $n: computed $(grep '"kind":"task"' "$journal" | grep -c '"role":"compute"')," \
        "verified $(grep '"kind":"task"' "$journal" | grep -c '"role":"verify"')," \
        "delegated ${delegated:-0} task(s)"
    done
    delegated_total=$(python3 - "$OUT" "$WORKERS" <<'PY'
import pathlib, re, sys
root, workers = pathlib.Path(sys.argv[1]), int(sys.argv[2])
pattern = re.compile(r"Delegated .* into \d+ child tasks")
print(sum(len(pattern.findall((root / f"w{n}" / "node.log").read_text(errors="replace")))
          for n in range(1, workers + 1)))
PY
)
    if [[ "$REQUIRE_DELEGATION" == 1 && "$delegated_total" -lt 1 ]]; then
      echo "FAIL: job assembled, but no worker logged a recursive delegation"
      for n in $(seq "$WORKERS"); do tail -n 40 "$OUT/w$n/node.log"; done
      exit 1
    fi
    echo "P2P recursive delegations observed: $delegated_total"
    if [[ "$REQUIRE_DHT_CAPACITY" == 1 ]] && grep -h 'MaxRecords' "$OUT"/o/*.log "$OUT"/w*/node.log 2>/dev/null; then
      echo "FAIL: the DHT record cache filled during this job"
      exit 1
    fi
    exit 0
  fi
done
echo "FAIL: no reassembled image after ${JOB_TIMEOUT_SECS} s (logs in $OUT)"
curl -s --max-time 5 "http://127.0.0.1:$API/jobs/$JOB"; echo
tail -n 40 "$OUT/orchestrator.log"
for n in $(seq "$WORKERS"); do echo "--- worker $n"; tail -n 20 "$OUT/w$n/node.log"; done
for n in $(seq "$WORKERS"); do echo "--- worker $n compute daemon"; tail -n 40 "$OUT/w$n/compute.log"; done
exit 1
