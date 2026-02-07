# Workloads Coverage Matrix (v1)

This document maps **catalog workloads** to **core features / failure modes** of the Silicium pipeline.
It is intentionally concise, versioned, and meant to evolve as new workloads are added.

- Source of truth for workloads: `catalog/workloads/**/manifest.yaml`
- Schema reference: `catalog/workloads/schema/workload-manifest-v1.schema.json`

## Legend

Features covered (columns):
- `SPLIT`: splitter pipeline (disasm/analysis/partitioning)
- `ARTF`: artifact generation (`summary.json`, fragments, metadata)
- `EXEC_EMU`: executor emulation backend
- `EXEC_NATIVE`: executor native backend (best-effort)
- `EXEC_DYNAMO`: DynamoRIO path (where applicable)
- `WORKER_QUEUE`: worker queue + scheduling
- `WORKER_OS`: OS routing policy (linux/windows)
- `VALIDATION`: verification workloads used as audits
- `IO_STDIN`: stdin ingestion / file inputs
- `IO_FILES`: output artifacts (hashes/reports)
- `DET`: determinism or bounded stochastic behavior
- `RES`: resource envelope stress (CPU/GPU/MEM)

Symbols:
- `✅` covered by workload
- `◐` partial / indirect coverage
- `—` not covered

## Matrix

| Workload | SPLIT | ARTF | EXEC_EMU | EXEC_NATIVE | EXEC_DYNAMO | WORKER_QUEUE | WORKER_OS | VALIDATION | IO_STDIN | IO_FILES | DET | RES |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `calcul/libm/sin` | ✅ | ✅ | ✅ | ◐ | — | ✅ | ◐ | ◐ (hash-audit) | — | ✅ | ✅ | cpu_light |
| `calcul/libm/exp` | ✅ | ✅ | ✅ | ◐ | — | ✅ | ◐ | ◐ (hash-audit) | — | ✅ | ✅ | cpu_light |
| `calcul/math-simulation` | ✅ | ✅ | ✅ | ◐ | — | ✅ | ◐ | ✅ (statistical-consistency) | — | ✅ | ◐ | cpu_heavy |
| `calcul/monte-carlo` | ✅ | ✅ | ✅ | ◐ | — | ✅ | ◐ | ✅ (statistical-consistency) | — | ✅ | ◐ | cpu_heavy/gpu_optional |
| `calcul/ml-inference` | ✅ | ✅ | ✅ | ◐ | — | ✅ | ◐ | ◐ (hash-audit) | — | ✅ | ✅ | gpu_optional |
| `calcul/rendering` | ✅ | ✅ | ✅ | ◐ | ✅ | ✅ | ◐ | ✅ (rendering-spotcheck) | — | ✅ | ✅ | gpu_optional |
| `calcul/video-encoding` | ✅ | ✅ | ✅ | ◐ | — | ✅ | ◐ | ✅ (hash-audit) | — | ✅ | ✅ | cpu_heavy |
| `calcul/data-compression` | ✅ | ✅ | ✅ | ◐ | — | ✅ | ◐ | ✅ (hash-audit) | — | ✅ | ✅ | cpu_heavy |
| `verification/hash-audit` | — | — | ✅ | ◐ | — | ✅ | ◐ | — | — | ✅ | ✅ | cpu_light |
| `verification/statistical-consistency` | — | — | ✅ | ◐ | — | ✅ | ◐ | — | — | ✅ | ◐ | cpu_heavy |
| `verification/rendering-spotcheck` | — | — | ✅ | ◐ | ✅ | ✅ | ◐ | — | — | ✅ | ✅ | gpu_optional |

## Gaps / Missing Coverage

1. `EXEC_NATIVE` hardening
   - Current workloads run native in best-effort mode only.
   - Need a dedicated native-friendly workload with deterministic, low-level syscalls.

2. `WORKER_OS` (cross-OS routing)
   - No workload explicitly tagged for Linux vs Windows routing policy validation.
   - Add a synthetic workload that forces OS routing to `skip/error` and validates telemetry.

3. `IO_STDIN` coverage
   - None of the current workloads exercise stdin input paths.
   - Add a micro-workload that feeds stdin and validates output.

4. `EXEC_DYNAMO` coverage
   - Only rendering spotcheck provides realistic coverage.
   - Add a smaller binary-focused workload for DynamoRIO startup/exit stability.

5. `RES` stress matrices
   - No memory-heavy or GPU-required workloads.
   - Add at least one `gpu_required` and one `memory_heavy` workload.

## Follow-up Issue Proposals

- Native-friendly micro workload (deterministic system-call baseline).
- OS routing policy workload (explicit linux/windows fragments).
- Stdin IO workload (read stdin, emit hash).
- DynamoRIO micro workload (fast startup + deterministic output).
- Resource stress workloads (gpu_required, memory_heavy).

## Maintenance

- Update this matrix when adding/removing workloads.
- Re-evaluate gaps after `executor --native` stabilization and new resource profiles.
