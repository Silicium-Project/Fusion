# Silicium networked demo helpers

This folder contains generic helpers to run demo workloads through real peer
HTTP/P2P nodes instead of local inline worker passes.

The mechanism is workload-agnostic:

1. an emitter publishes task envelopes and P2P content refs;
2. a peer with the required role receives the task through `/tasks/dispatch`;
3. that peer fetches the input content through the Silicium P2P HTTP layer;
4. the peer computes or verifies according to the workload id;
5. the peer returns `result.<task-id>.json` to the emitter through
   `/results/dispatch`;
6. the emitter can reassemble or finalize using the returned refs.

`raytracer` is the current workload plugged into this path. Another workload can
reuse the same network flow if it provides:

- a compute workload id;
- a verify workload id;
- a splitter/fragment spec;
- a reassembler for verified outputs.

## Start remote workers

Run from `Network/`.

On the compute machine:

```powershell
.\demo\networked\start-node.cmd worker-1 compute 46101 http://EMITTER_IP:46100 WORKER_IP demo-mesh 120
```

On verifier machines:

```powershell
.\demo\networked\start-node.cmd verifier-1 verify 46102 http://EMITTER_IP:46100 VERIFIER1_IP demo-mesh 90
.\demo\networked\start-node.cmd verifier-2 verify 46103 http://EMITTER_IP:46100 VERIFIER2_IP demo-mesh 70
```

Use the same `mesh-key` on every node for the demo network.

The last argument is the local demo reputation announced by the node. When
Solana reputation sync is enabled, the scheduler also uses the role-specific
on-chain reputation (`compute`, `verify`, `storage`). The selection is weighted
by reputation and capacity, then penalized by current dispatch load so one strong
peer can receive more work without monopolizing every fragment.

## Run the raytracer workload in network mode

On the emitter machine:

```powershell
py .\workloads\raytracer\run_network_job.py .\workloads\raytracer\examples\silicium-multi-fragment-scene.cfg --job-id raytracer-net-001 --node-mode network --network-advertise-host EMITTER_IP --network-seed-peers http://WORKER_IP:46101,http://VERIFIER1_IP:46102,http://VERIFIER2_IP:46103 --network-mesh-key demo-mesh
```

Optional reputation gates:

```powershell
py .\workloads\raytracer\run_network_job.py .\workloads\raytracer\examples\silicium-multi-fragment-scene.cfg --job-id raytracer-net-002 --node-mode network --network-advertise-host EMITTER_IP --network-seed-peers http://WORKER_IP:46101,http://VERIFIER1_IP:46102 --network-mesh-key demo-mesh --min-compute-reputation 50 --min-verify-reputation 40
```

Add `--devnet-trace` when the network run succeeds and you want to write the
job/split/compute/vote/finalize trace to Solana Devnet.
