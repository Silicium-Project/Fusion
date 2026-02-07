# Workload and Golden Corpus Alignment Policy

This policy defines how catalog workloads align with golden corpus fixtures.

## Scope

- Catalog manifests in `catalog/workloads/**/manifest.yaml`
- Golden fixtures index in `catalog/workloads/fixtures/fixtures.json`
- Critical family policy in `catalog/workloads/fixtures/alignment-policy.json`

## Family mapping rule

- A workload family is `<category>/<family>` from workload id.
- Example: `calcul/libm/sin` maps to family `calcul/libm`.
- A family is covered when at least one fixture entry maps to the same family.

## Critical families

- Critical families are listed in `alignment-policy.json`.
- Critical families must always have at least one golden fixture entry.
- CI or release checks should run strict alignment validation.

## Validation command

Run:

```bash
./silicium workload alignment
```

Strict mode:

```bash
./silicium workload alignment --strict
```

Machine-readable:

```bash
./silicium workload alignment --json
```

## Review checklist

- New critical workload family: add fixture mapping in the same PR.
- Existing critical family change: update or extend fixture entries.
- Manifest id changes: verify family mapping still resolves correctly.
