# Network stability criteria

The active Network core is the Python/Rust distributed runtime, the Solana
layer, and the workload path. The historical C++ fragment pipeline is no
longer an acceptance target.

## Baseline

- Python 3.11 or newer with `requirements-dev.txt` installed.
- Rust toolchain for `networked/*` and `workloads/raytracer/native`.
- Docker only for the Compose proxy, world testbed, and E2E checks.
- Solana and Anchor toolchains for the on-chain workflow.

## Acceptance checks

```bash
make check
make test
make raytracer-test
python3 ./silicium workload lint
python3 ./silicium workload golden --strict
```

The full CI path additionally runs the Rust P2P smoke test, the Solana localnet
build/test, Docker E2E, and the proxy health check. A missing optional runtime
such as Docker or Cargo must be reported as skipped locally; CI runners that
claim the corresponding job must provide it.

## Single command

```bash
CORE_CHECK_MODE=quick CORE_CHECK_SCOPE=platform bash ci/core_check.sh
CORE_CHECK_MODE=full CORE_CHECK_SCOPE=platform bash ci/core_check.sh
```

`CORE_CHECK_SCOPE=all` remains accepted as a compatibility alias for
`platform`. No scope may refer to the removed `splitter`, `executor`, or
`worker` directories.
