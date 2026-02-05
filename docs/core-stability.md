# Core Stability Criteria

This document defines what "stable" means for the core modules.
Scope: splitter, executor, worker, CLI orchestration, and optional Docker infra.

## Prerequisites (baseline)
- Linux recommended
- Windows: Docker Desktop supported (no WSL requirement when using `silicium check --runner docker`)
- `bash`, `make`, `g++`
- `python3` (or `python`) with `pytest` and `pyyaml`
- Docker (optional, required for full infra and DynamoRIO checks)

## Acceptance Criteria (by module)

### Splitter
- `make -C splitter demo` completes with exit code 0.
- `splitter/run_output/demo/summary.json` exists and is non-empty.

### Executor (emulation)
- `make -C splitter demo` already exercises `fragment_executor` in emulation.
- Running on the demo summary returns exit code 0.

### Worker (core modes)
- `./worker/worker --summary <summary.json> --mode emu --output json` exits 0.
- Optional: `--mode native` only if enabled (known instability on some fragments).

### CLI (`silicium`)
- `./silicium workload list` exits 0 and prints entries.
- `./silicium workload show calcul/math-simulation --readme` exits 0.

### Python tests (entrypoint + manifests)
- `python -m pytest` exits 0.

## Optional (Docker)

### Proxy smoke (TLS + healthz)
- `./silicium smoke` exits 0.

### Worker DynamoRIO
- `./worker/worker --summary <summary.json> --mode dynamo --output json` exits 0
  (requires Docker + `dynamorio-runner` image).

## Single Command Check

Use `ci/core_check.sh` or `./silicium check`:

```
CORE_CHECK_MODE=quick ./ci/core_check.sh
CORE_CHECK_MODE=full ./ci/core_check.sh

./silicium check
./silicium check --full
./silicium check --native
./silicium check --dynamo --require-docker
./silicium check --runner docker
```

Docker runner defaults to the lightweight image `silicium/core-check:lite`
(built from `docker/core-check/Dockerfile`). Override with
`SILICIUM_CORE_CHECK_IMAGE` if needed.

Environment flags:
- `CORE_CHECK_MODE=quick|full` (default: `quick`)
- `CORE_CHECK_NATIVE=1` to test native execution
- `CORE_CHECK_WITH_DOCKER=0|1|auto` (default: `auto`)
- `CORE_CHECK_REQUIRE_DOCKER=1` to fail if Docker is missing
- `CORE_CHECK_RUN_DYNAMO=1` to run the DynamoRIO mode
- `CORE_CHECK_CLEAN=1` to force a clean rebuild (default: enabled in Docker)
- `CORE_CHECK_JOBS=<n>` to limit make parallelism (overrides default JOBS)

Resource limiting tips:
- `./silicium check --jobs 2` limits build parallelism to 2.
- `SILICIUM_MAX_JOBS=2 ./silicium check` (same effect via env var).
- `./silicium check --runner docker --docker-cpus 2 --docker-memory 4g` limits Docker CPU/memory.
