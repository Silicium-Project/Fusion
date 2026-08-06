# CI/CD Topology

This document describes the intended execution model for Fusion.

## Goal

Keep the workflow traceable:

- GitHub stores the source, issues, pull requests, and audit trail.
- The VPS executes the production path.
- Self-hosted runners on the VPS are preferred for any automation that must run
  close to production state.
- The visible lifecycle is `Build` -> `Test` -> `Deploy`.

## Current contract

### GitHub

GitHub should be used as:

- source control;
- trigger surface;
- review and history;
- status display.

GitHub should not be the primary compute plane for deploy, E2E, or release
validation.

### VPS

The VPS is the execution plane for:

- submodule synchronization;
- deployment;
- post-deploy validation;
- container-based E2E;
- release marker publication;
- mirrors that need to follow the production state.

The VPS may also host a self-hosted GitHub Actions runner so the workflows still
appear in GitHub while actually executing on VPS hardware.

### Transitional exception

The desktop Windows packaging lane may still need a dedicated Windows runner
until the build is fully cross-built or moved to a Windows-capable host on the
same operational plane.

## Canonical flow

1. `sync-submodules.yml` detects new `main` heads for `BackEnd`, `FrontEnd`,
   and `Network`.
2. `submodule-ci-gate.yml` fails immediately if any of those `main` heads is
   red, incomplete, or missing.
3. `build.yml` produces the Linux release bundles on the VPS runner.
4. `test.yml` validates the web stack, Network core, Docker E2E, and the P2P
   smoke path on the VPS runner.
5. `deploy-vps.yml` pulls the exact Fusion ref on the VPS, updates submodules,
   rebuilds services, deploys, and runs post-deploy checks.
6. `deploy/compose/e2e.sh` validates the real container path on the VPS.
7. `mirror-epitech.yml` mirrors the exact Fusion tree into the Epitech repo
   after the composition is published.

## Rules

- Do not add a second deployment path outside the VPS without documenting why
  it exists.
- Do not let a green Fusion workflow mask a red submodule `main`.
- Do not use `git submodule update --remote` in production deploy steps unless
  the target SHA is also gated by CI.
- Keep the workflow surface small: one canonical deploy path, one canonical
  rollback path, plus one explicit external mirror path if it is still needed.

## Workflow inventory

### Fusion root

- `sync-submodules.yml`: canonical scheduler for publishing exact gitlinks.
- `submodule-ci-gate.yml`: reusable hard gate for `BackEnd`, `FrontEnd`, and
  `Network` `main` health.
- `build.yml`: canonical Linux bundle build workflow.
- `test.yml`: canonical web, Network core, Docker E2E, and P2P smoke workflow.
- `deploy-vps.yml`: canonical production deploy and VPS validation path.
- `rollback-vps.yml`: manual recovery path only.
- `mirror-epitech.yml`: explicit external mirror path to the Epitech repo.

### Submodules

- `BackEnd/.github/workflows/ci.yml`: backend build/test lane on the VPS
  runner.
- `FrontEnd/.github/workflows/ci.yml`: frontend build/test lane on the VPS
  runner.
- `Network/.github/workflows/ci.yml`: canonical orchestrator for `Network`.
- `Network/.github/workflows/{tests,p2p-node,solana-layer-ci-only,codeql}.yml`:
  reusable or manual lanes underneath the canonical orchestrator.

### Immediate cleanup target

The next simplification should focus on the remaining duplication between:

- `deploy-vps.yml` validation jobs;
- `Network/.github/workflows/ci.yml` and its reusable lane files;
- the backend/frontend CI lanes and the Fusion-level gate if their checks can
  be collapsed further without losing signal.
