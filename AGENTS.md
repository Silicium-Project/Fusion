# Network repository guide

Network is the distributed-runtime repository composed by Fusion. It contains
the peer-to-peer node, the Solana integration, the workload catalog, the
developer CLI, and the local/test infrastructure used by those components.

## Canonical components

- `crates/p2p-node/`: peer discovery, authenticated peer HTTP, content
  transfer, task dispatch, and gossip.
- `crates/node-core/`: Rust node runtime and transport primitives.
- `crates/compute-daemon/`: compute-role daemon used by the node stack.
- `crates/reputation-bridge/`: bridge consumed by Fusion's production
  Compose stack.
- `tools/network_node.py`, `tools/dev/e2e/bootstrap_orchestrator.py`, and the RPC,
  telemetry, receipt, and update-manifest tools: Python control-plane helpers.
- `solana-layer/`: Anchor program, SDK, migrations, IDL generation, and tests.
- `silicium-layer-dashboard/`: Vite dashboard for network/Solana inspection.
- `workloads/raytracer/`: the current end-to-end workload, including its Rust
  native implementation.
- `catalog/`, `proto/`, `i18n/`, `tests/`, and `docs/`: contracts, fixtures,
  localization, validation, and project documentation.

The former C++ `splitter`/`executor`/`worker` chain, Qt viewer, assembler demos,
PE corpus, and generated coverage reports are intentionally absent. They are
historical material in Git history, not part of the active Network product.

## Infrastructure ownership

`infra/docker-compose.yml` owns local Network/Solana nodes and the local proxy.
`infra/docker-compose.world.yml` owns the optional world/Solana integration
testbed. `infra/bootstrap/` contains bootstrap fixtures for that testbed.
Production site deployment belongs to Fusion (`deploy/compose`), not this
repository. Keep credentials in local env files; commit only
`infra/.env.example`-style templates.

## Common checks

**Tests et CI**
- Tests Python: `tests/test_entrypoint.py`, `tests/test_manifests.py`.
- CI GitHub Actions: `.github/workflows/ci.yml`, `release.yml`.
- Scripts locaux: `ci/e2e.sh`, `ci/test_images.sh`.

The canonical GitHub workflow is `.github/workflows/ci.yml`. It validates the
Python/runtime path, Rust P2P crates, Solana layer, raytracer, Docker E2E, and
proxy/P2P smoke checks. It must not reintroduce the removed C++ jobs.

## Generated state

Builds, ledgers, caches, logs, validator output, and native Cargo targets are
ignored by `.gitignore`. Do not add generated runtime state, secrets, or local
wallets to the repository.
