# P2P Node Backlog - Binary Bitfield Edition (2026-08-01)

This document translates the proposed architecture into executable backlog items for the Network repository.

Policy alignment:
- Parent issue format follows `.github/ISSUE_TEMPLATE/parent-umbrella.md`.
- Hygiene and closure policy follows `docs/backlog-hygiene.md`.

## Parent Umbrella Issue Draft

Title:
- [Parent] Binary bitfield scheduling, dual runtime execution, and VPS bootstrap deployment

Objective:
- Deliver a production-ready node foundation for hardware-aware scheduling using binary bitfields, Bayesian dispatch, DAG splitting, and containerized deployment.

Child issues:
- [ ] #1 Implement HardwareBucket binary bitfield
- [ ] #2 Initialize libp2p + Kademlia overlay
- [ ] #3 Add Beta distribution persistence model
- [ ] #4 Implement Thompson Sampling core
- [ ] #5 Add sparse affinity cold-start fallback
- [ ] #6 Integrate WASM runtime path
- [ ] #7 Integrate OCI runtime path for GPU workers
- [ ] #8 Implement DAG parser and dependency scheduler
- [ ] #9 Create multi-stage Dockerfile for silicium-node
- [ ] #10 Add CI/CD pipeline for lint, tests, build, publish
- [ ] #11 Deploy bootstrap super-node on VPS

Closure criteria:
- [ ] All 11 child issues are closed.
- [ ] P2P bootstrap path can be validated end-to-end in staging.
- [ ] Final summary note posted with delivered artifacts and remaining risks.

Review cadence:
- Weekly parent issue review.
- Milestone-end re-scope review.

---

## Issue #1 - Implement HardwareBucket binary bitfield

Type: feature
Priority: P0
Labels: `network`, `scheduler`, `performance`, `rust`
Depends on: none

Description:
- Replace text hardware descriptor with a native bitfield (`u16` first, extendable to `u32`).

Technical scope:
- Define fixed bit layout for:
  - VRAM class
  - GPU acceleration (CUDA, Metal, ROCm, Vulkan compute as reserved/optional)
  - SIMD width
  - OS family
- Add encode/decode helpers.
- Add Hamming distance helper using `count_ones()` on XOR.

Acceptance criteria:
- Deterministic encoding and decoding for all supported classes.
- Distance function executes in O(1) and is covered by unit tests.
- Unknown bits are ignored or rejected according to explicit policy.

Test plan:
- Unit tests for bit masks and round-trip conversion.
- Property test: `decode(encode(x)) == x` for valid domain.

---

## Issue #2 - Initialize libp2p + Kademlia overlay

Type: feature
Priority: P0
Labels: `network`, `p2p`, `kademlia`, `rust`
Depends on: #1

Description:
- Build node networking foundation using libp2p and Kademlia DHT.

Technical scope:
- Configure transports (TCP and QUIC).
- Configure stream muxing.
- Wire Kademlia record put/get for hardware scores and task metadata.
- Add bootstrap peer configuration entry points.

Acceptance criteria:
- Two local nodes can connect and exchange Kademlia records.
- Record schema for hardware/task keys is versioned.
- Peer bootstrap list can be configured via env and CLI.

Test plan:
- Integration test with 2-3 local peers.
- Smoke test for node restart and DHT rejoin.

---

## Issue #3 - Add Beta distribution persistence model

Type: feature
Priority: P0
Labels: `scheduler`, `bayesian`, `serialization`, `rust`
Depends on: #2

Description:
- Implement lightweight `Beta { alpha, beta }` state model for affinity reputation.

Technical scope:
- Add struct and update methods (success/failure increments).
- Add compact serialization (bincode preferred) with version tag.
- Define DHT key format for affinity entries.

Acceptance criteria:
- Serialization round-trip is stable across process restart.
- Backward compatibility behavior is explicit for version mismatch.

Test plan:
- Unit tests for update rules.
- Unit tests for serialization round-trip and invalid payload handling.

---

## Issue #4 - Implement Thompson Sampling core

Type: feature
Priority: P0
Labels: `scheduler`, `bayesian`, `dispatch`, `rust`
Depends on: #3

Description:
- Implement candidate scoring using Thompson Sampling from Beta posteriors.

Technical scope:
- Integrate PRNG and Beta sampling (`rand_distr`).
- Compute score per candidate and select argmax.
- Add deterministic seeded mode for tests.

Acceptance criteria:
- Selection prefers higher posterior over repeated trials.
- Deterministic test mode reproduces same sequence.

Test plan:
- Statistical sanity tests over Monte Carlo runs.
- Regression tests with fixed seeds.

---

## Issue #5 - Add sparse affinity cold-start fallback

Type: feature
Priority: P0
Labels: `scheduler`, `dht`, `cold-start`, `rust`
Depends on: #1, #3, #4

Description:
- Handle missing affinity entries by deriving default prior with high variance.

Technical scope:
- If `aff:HW:TASK` missing, compute default prior from scaling law `(H / T)`.
- Use high-variance prior baseline (`alpha=2, beta=2`) when uncertain.
- Do not write to DHT pre-execution.
- Persist posterior only after execution outcome.

Acceptance criteria:
- Missing affinity never blocks scheduling.
- DHT write occurs only after task completion event.

Test plan:
- Unit tests for fallback path.
- Integration test ensuring no early DHT insertion.

---

## Issue #6 - Integrate WASM runtime path

Type: feature
Priority: P1
Labels: `runtime`, `wasm`, `sandbox`, `rust`
Depends on: #8

Description:
- Add sandboxed runtime for lightweight CPU tasks on heterogeneous workers.

Technical scope:
- Integrate Wasmtime (or WAMR if footprint constraints require).
- Define WASI boundary for input/output buffers.
- Add memory and syscall guardrails.

Acceptance criteria:
- Worker can execute signed WASM task payload successfully.
- Runtime enforces memory limits and timeout.

Test plan:
- Golden-path WASM execution test.
- Failure-path tests (timeout, memory cap, invalid module).

---

## Issue #7 - Integrate OCI runtime path for GPU workers

Type: feature
Priority: P1
Labels: `runtime`, `docker`, `gpu`, `nvidia`
Depends on: #8, #9

Description:
- Add heavy-task execution path via OCI containers for GPU workloads.

Technical scope:
- Connect node runtime to Docker socket or containerd API.
- Support GPU runtime flags and NVIDIA toolkit integration.
- Add container lifecycle controls (create/start/stop/prune).

Acceptance criteria:
- Node can run a GPU-tagged job in OCI runtime.
- Runtime has explicit resource limits and cleanup behavior.

Test plan:
- Integration test on GPU-capable runner.
- Negative test when GPU runtime is unavailable.

---

## Issue #8 - Implement DAG parser and dependency scheduler

Type: feature
Priority: P0
Labels: `scheduler`, `dag`, `pipeline`, `rust`
Depends on: #4, #5

Description:
- Parse render/task graph and enforce dependency-safe dispatch.

Technical scope:
- Define DAG node and edge model.
- Implement topological readiness queue.
- Enforce parent completion before child dispatch (for compositing over geometry passes).

Acceptance criteria:
- No child task is dispatched before all required parents complete.
- Scheduler can recover from failed node and propagate retry/cancel policy.

Test plan:
- Unit tests on DAG ordering.
- Integration tests with mixed success/failure branches.

---

## Issue #9 - Create multi-stage Dockerfile for silicium-node

Type: infra
Priority: P0
Labels: `docker`, `build`, `runtime`, `release`
Depends on: #2

Description:
- Containerize node using a hardened multi-stage Docker build.

Technical scope:
- Build stage: Rust toolchain and compile with reproducible flags.
- Runtime stage: minimal base image.
- Expose required P2P and control ports.
- Include healthcheck.

Acceptance criteria:
- Image builds in CI and runs with non-root user.
- Startup and health endpoint pass in containerized smoke test.

Test plan:
- CI image build test.
- Container smoke test with bootstrap peer env.

---

## Issue #10 - Add CI/CD pipeline for lint, tests, build, publish

Type: infra
Priority: P0
Labels: `ci`, `cd`, `github-actions`, `release`
Depends on: #1, #3, #4, #9

Description:
- Automate quality gates and artifact publication.

Technical scope:
- Job A: `cargo fmt --check`, `cargo clippy -- -D warnings`, unit/integration tests.
- Job B: cross-build for `x86_64` and `aarch64`.
- Job C: Docker image build and push to registry.
- Add cache strategy for Rust dependencies.

Acceptance criteria:
- PRs are blocked on lint/test failures.
- Tagged release produces multi-arch images.

Test plan:
- Verify PR workflow status checks.
- Verify release workflow emits image digest outputs.

---

## Issue #11 - Deploy bootstrap super-node on VPS

Type: infra
Priority: P0
Labels: `deploy`, `vps`, `bootstrap`, `kademlia`
Depends on: #2, #9, #10

Description:
- Deploy stable bootstrap node as DHT entrypoint for production network.

Technical scope:
- Add VPS `docker-compose.yml` for bootstrap service.
- Configure firewall for required TCP/UDP ports.
- Add TLS termination strategy and persistent volume mounts.
- Add operations runbook for restart, backup, and key rotation.

Acceptance criteria:
- Public node is reachable from at least two external peers.
- Restart preserves required node state and identity.
- Basic observability endpoint is available.

Test plan:
- External connectivity check from remote peer(s).
- Disaster drill: container restart and data persistence validation.

---

## Suggested Execution Order

Milestone M1 (Core scheduling):
- #1, #2, #3, #4, #5

Milestone M2 (Task graph + runtimes):
- #8, #6, #7

Milestone M3 (Ship and operate):
- #9, #10, #11

## Risk Register

- Transport interoperability risk between TCP and QUIC stacks.
- Runtime trust boundary risk (WASM and OCI supply chain).
- Cold-start bias risk if `(H / T)` heuristic is poorly calibrated.
- VPS bootstrap centralization risk (single point of entry).

## Definition of Done (Program Level)

- Binary bitfield-based affinity and Bayesian dispatch are active in scheduler path.
- DAG dependencies are enforced in dispatch and execution order.
- Both WASM and OCI execution paths are available behind capability checks.
- Multi-arch images are built in CI and published.
- Bootstrap node deployment is documented, reproducible, and monitored.