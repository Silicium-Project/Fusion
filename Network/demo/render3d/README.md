# Render3D manual demo

This folder contains the first simple end-to-end demo path for Silicium.
The reusable render implementation now lives in `Network/workloads/render3d`.
The scripts here are orchestration scenarios around that workload: local files,
node passes, network mode and Devnet tracing.

The input scene is provided manually as a JSON file. The demo script writes a
local deterministic preview, hashes/manifests, then optionally queues compute
and verify task envelopes into the Silicium network ingress directory.

The role-aware node now knows this workload through the workload entrypoints:

- `compute` reads `scene.json` through `p2p_ref`, runs the workload compute entrypoint, and
  publishes the rendered PPM through the local P2P cache.
- `verify` reads the rendered PPM through `p2p_ref`, reads the original
  `scene.json` through `scene_p2p_ref`, runs the workload verify entrypoint, and compares
  hashes.

## Files

- `scene.json`: example 3D scene.
- `render3d_demo.py`: compatibility wrapper around `Network/workloads/render3d`.
- `submit-render3d.cmd`: Windows helper.
- `run_full_demo.py`: full compute-then-verify demo orchestrator.
- `run-full-demo.cmd`: Windows helper for the full demo.
- `run_fragmented_demo.py`: fragmented compute/verify/reassemble orchestrator.
- `run-fragmented-demo.cmd`: Windows helper for the fragmented demo.

## Workload entrypoints

The reusable render3d contract is:

```powershell
py .\workloads\render3d\split.py .\demo\render3d\scene.json --output .\.silicium\split.json
py .\workloads\render3d\compute.py --scene .\demo\render3d\scene.json --output .\.silicium\fragment.ppm --y-start 0 --y-end 100
py .\workloads\render3d\verify.py --scene .\demo\render3d\scene.json --result .\.silicium\fragment.ppm --y-start 0 --y-end 100
py .\workloads\render3d\reassemble.py --fragment .\.silicium\fragment-0.ppm --fragment .\.silicium\fragment-1.ppm --output .\.silicium\render.ppm --png .\.silicium\render.png
```

A future raytracer should provide the same shape of entrypoints without changing
the network core.

Generated artifacts are written outside the demo folder:

```txt
Network/.silicium/demo/render3d/<task-id>/
```

The local demo preview writes both:

- `output/render.ppm`: raw deterministic render output used by the compute hash.
- `output/render.png`: browser/Windows-friendly preview image.

Queued task envelopes go to:

```txt
Network/.silicium/mcp/export/
```

## Render locally only

```powershell
py .\demo\render3d\render3d_demo.py render .\demo\render3d\scene.json --task-id render-demo-001
```

## Convert an existing PPM to PNG

```powershell
py .\demo\render3d\render3d_demo.py convert .\.silicium\demo\render3d\render-demo-001\output\render.ppm
```

## Queue into the Silicium network

From `Network/`:

```powershell
.\demo\render3d\submit-render3d.cmd .\demo\render3d\scene.json --task-id render-demo-001
```

This writes two task envelopes:

- `render-demo-001`: compute task using the scene file.
- `render-demo-001-verify`: verify task checking the rendered image hash and
  recomputing the scene.

If a role-aware node is running with the same export directory, it can consume
these queues and publish `result.<task-id>.json` files.

## Run the full manual demo

From `Network/`:

```powershell
.\demo\render3d\run-full-demo.cmd .\demo\render3d\scene.json --task-id render-demo-001
```

The runner performs the first demo path end-to-end:

1. Render a deterministic local preview and write `manifest.json`.
2. Queue the compute task.
3. Start one node pass for `compute` and wait for
   `result.<task-id>.json`.
4. Extract the real `output_ref` produced by compute.
5. Queue the verify task using that `output_ref`.
6. Start one node pass for `verify` and wait for
   `result.<task-id>-verify.json`.
7. Write `full-demo-summary.json` in the generated job directory.

By default, `--node-mode auto` tries the real CLI node first. On Windows, if the
node cannot create its P2P identity because `openssl` is missing, the runner
falls back to an inline demo pass that uses the same render/verify runtime but
does not start the signed P2P peer layer. Use `--node-mode cli` to require the
real node, or `--node-mode inline` for a local smoke test. The runner also looks
for OpenSSL in common Windows install paths before starting the node.

To install/check OpenSSL through the project launcher:

```powershell
.\start-silicium-windows.cmd -InstallSystemDeps -SkipDashboard -SkipWorldNode
```

Then rerun the demo with the real node enforced:

```powershell
.\demo\render3d\run-full-demo.cmd .\demo\render3d\scene.json --task-id render-demo-002 --node-mode cli
```

When using the shared `.silicium/mcp/export` directory, old queued tasks may be
processed before the current demo task. The runner therefore repeats node sweeps
until the expected `result.<task-id>.json` appears. Increase the limit if the
queue is busy:

```powershell
.\demo\render3d\run-full-demo.cmd .\demo\render3d\scene.json --task-id render-demo-002 --node-mode cli --node-sweeps 30
```

## Run the fragmented demo

From `Network/`:

```powershell
.\demo\render3d\run-fragmented-demo.cmd .\demo\render3d\scene.json --job-id render-frag-001 --fragments 4 --node-mode cli
```

This demo splits the render into horizontal bands. Each band becomes a compute
task, then a verify task, then the script reassembles all verified fragment
outputs into:

```txt
Network/.silicium/demo/render3d/<job-id>/reassembled/render.png
```

Each fragmented run uses its own queue/export directory by default:

```txt
Network/.silicium/demo/render3d/<job-id>/export
```

Use a fresh `--job-id` for each Devnet demo. Reusing the same job id with a
different fragment count can mix old local files and old queued tasks. The script
therefore refuses an existing job directory unless `--reuse-job-dir` is passed
explicitly.

Without `--devnet-trace`, the fragmented demo records `devnet_trace.status =
not_requested` and stays P2P/local only.

To also write the verified fragment path to Solana Devnet, run:

```powershell
.\demo\render3d\run-fragmented-demo.cmd .\demo\render3d\scene.json --job-id render-frag-001 --fragments 4 --node-mode cli --devnet-trace
```

This creates a Devnet test mint, job, storage commitment, compute worker, two
verifier workers, fragment submissions, verifier votes, and finalization. The
heavy files still stay in the P2P/local storage layer; Devnet stores hashes,
state transitions and payment/reputation events. The trace is written beside the
demo summary as `devnet-trace.json`.

The Devnet trace requires a Solana wallet keypair and Devnet SOL. If the Solana
CLI is not installed, use the project helper:

```powershell
.\demo\render3d\prepare-devnet-wallet.cmd
```

If the RPC airdrop returns `429 Too Many Requests`, use
https://faucet.solana.com with the printed `public_key`, then rerun the helper
to confirm the balance.

If your wallet is elsewhere, pass it explicitly:

```powershell
.\demo\render3d\run-fragmented-demo.cmd .\demo\render3d\scene.json --job-id render-frag-001 --fragments 4 --node-mode cli --devnet-trace --solana-wallet C:\path\to\id.json
```

## Run the recursive auto-split demo

The auto-split demo lets the network-side orchestrator estimate render
complexity and recursively split a task until each leaf is small enough.

```powershell
.\demo\render3d\run-auto-split-demo.cmd .\demo\render3d\scene.json --job-id render-auto-001 --complexity-threshold 60000 --node-mode cli
```

For the default scene, a threshold around `60000` produces this shape:

```txt
root fragment 0
  parent fragment 1
    leaf fragment 2
    leaf fragment 3
  parent fragment 4
    leaf fragment 5
    leaf fragment 6
```

Only leaf fragments are computed and verified through the P2P/node queue. The
summary stores the full split tree in `auto-split-demo-summary.json`, then
reassembles the verified leaves into:

```txt
Network/.silicium/demo/render3d/<job-id>/reassembled/render.png
```

To also trace the recursive split on Devnet:

```powershell
.\demo\render3d\run-auto-split-demo.cmd .\demo\render3d\scene.json --job-id render-auto-001 --complexity-threshold 60000 --node-mode cli --devnet-trace --devnet-tx-delay-ms 2500
```

With `--devnet-trace`, the trace script creates the job with one root fragment,
claims the root, calls `propose_fragment_split`, `approve_fragment_split`, and
`create_sub_fragment` recursively, then claims/submits/votes only the leaf
fragments and finalizes the job.

## Run auto-split through real network nodes

The `network` node mode publishes the same generic task envelopes, but the
orchestrator does not execute compute/verify locally. It starts a peer HTTP node
with only the `resource` role, dispatches compute/verify tasks to peers that
advertise the required role, waits for returned results, then reassembles the
verified outputs.

Start remote nodes first, from `Network/`:

```powershell
.\demo\networked\start-node.cmd worker-1 compute 46101 http://ORCHESTRATOR_IP:46100 WORKER_IP demo-mesh 120
.\demo\networked\start-node.cmd verifier-1 verify 46102 http://ORCHESTRATOR_IP:46100 VERIFIER1_IP demo-mesh 90
```

Then run the orchestrator:

```powershell
.\demo\render3d\run-auto-split-demo.cmd .\demo\render3d\scene.json --job-id render-net-001 --node-mode network --network-advertise-host ORCHESTRATOR_IP --network-seed-peers http://WORKER_IP:46101,http://VERIFIER1_IP:46102 --network-mesh-key demo-mesh
```

The final `start-node.cmd` argument is the node's local demo reputation. The
generic scheduler ranks peers with role-specific reputation, local reputation,
capacity, and current dispatch load. You can also require minimum reputation:

```powershell
.\demo\render3d\run-auto-split-demo.cmd .\demo\render3d\scene.json --job-id render-net-002 --node-mode network --network-advertise-host ORCHESTRATOR_IP --network-seed-peers http://WORKER_IP:46101,http://VERIFIER1_IP:46102 --network-mesh-key demo-mesh --min-compute-reputation 50 --min-verify-reputation 40
```

This path is workload-generic at the network layer: render3d only provides the
split policy, compute workload id, verify workload id, and reassembler.

## Write task JSON without queuing

```powershell
py .\demo\render3d\render3d_demo.py submit .\demo\render3d\scene.json --task-id render-demo-001 --no-queue
```
