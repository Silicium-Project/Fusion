# Workload fixtures policy

This document defines how workload datasets and fixtures are stored, versioned, and verified.

Alignment rules are defined in `docs/workload-alignment-policy.md`.

## Goals

- Deterministic inputs for testing and reproducibility.
- Traceable updates with explicit versioning.
- Integrity validation via SHA-256 hashes.

## Storage layout

```
catalog/workloads/fixtures/
  fixtures.json
  <workload-family>/
    <workload-name>/
      v<major>/
        <files...>
```

Example:

```
catalog/workloads/fixtures/verification/hash-audit/v1/sample.txt
```

## Index format

The canonical index is `catalog/workloads/fixtures/fixtures.json`.

Fields per entry:

- `id`: workload id (matches `manifest.yaml` `id`).
- `version`: workload version.
- `path`: path relative to `catalog/workloads/fixtures/`.
- `sha256`: lowercase SHA-256 hash.

## Validation

Run:

```
./silicium workload fixtures
```

Use `--json` for a machine-readable report.

## Update workflow

1. Add new fixtures under a new versioned folder (`v2`, `v3`, ...).
2. Update `fixtures.json` with new entries and hashes.
3. Keep old entries unless explicitly deprecated in a changelog.

## Replacement policy

- Never overwrite existing files in place.
- Always add new versioned fixtures and update the index.
- Deletions require a documented reason and explicit removal from the index.

## Determinism and reproducibility

- `deterministic`: expected identical output for identical inputs.
- `bounded_stochastic`: output may vary but stays within an explicit tolerance.
- `stochastic`: non-deterministic, must include a rationale and `non_deterministic` tag.

For deterministic workloads, fixtures should include:

- A fixed preset (`presets.default`) with stable inputs.
- A reproducibility note in the workload README.
 - A `./silicium workload repro --workload <id>` check entry.
