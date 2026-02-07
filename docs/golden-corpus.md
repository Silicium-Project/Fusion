# Golden Corpus Policy

This document defines deterministic reference cases for workload regression checks.

## Files

- `catalog/workloads/golden/golden-corpus.json`: canonical case list.
- `catalog/workloads/fixtures/fixtures.json`: fixture integrity index.
- `catalog/workloads/fixtures/alignment-policy.json`: critical family coverage rules.

## Case contract

Each case includes:

- `id`: workload id.
- `preset`: preset name used to render a deterministic plan.
- `expected_plan_hash`: SHA-256 hash of normalized deterministic plan material.

## Validation command

Run:

```bash
./silicium workload golden --strict
```

Machine-readable:

```bash
./silicium workload golden --json
```

## Update workflow

When a deterministic workload plan changes intentionally:

1. Update manifests/presets.
2. Recompute expected hashes by running `./silicium workload golden --json`.
3. Update `expected_plan_hash` values in `golden-corpus.json`.
4. Include rationale in PR notes.
