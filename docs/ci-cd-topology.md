# CI/CD Topology

This document describes the intended execution model for Fusion.

## Goal

Keep the workflow traceable:

- GitHub stores the source, issues, pull requests, and audit trail.
- The VPS executes the production path.
- Self-hosted runners on the VPS execute the active CI, compilation, test, and
  deployment path.
- GitHub-hosted runners are an optional acceleration lane only when Actions
  billing is enabled and covered; they are not assumed to be available.
- The visible lifecycle is `Build` -> `Test` -> `Deploy`.

## Current contract

### GitHub

GitHub should be used as:

- source control;
- trigger surface;
- review and history;
- status display.

GitHub is not the primary compute plane for production deploy, post-deploy
validation, or the active CI lanes. CI E2E and compilation may use
GitHub-hosted capacity only when covered Actions usage is explicitly
available.

### VPS

The VPS is the execution plane for:

- submodule synchronization;
- deployment;
- post-deploy validation;
- container-based E2E;
- release marker publication;
- mirrors that need to follow the production state.

The VPS may also host a self-hosted GitHub Actions runner so the workflows still
appear in GitHub while executing on VPS hardware.

The bootstrap keeps the required runners and adds one optional runner for
`Fusion` and one for `Network` with the same `fusion-linux` label. This lets
independent jobs run concurrently on the VPS without changing the check set.
Set `SILICIUM_EXTRA_RUNNER_COUNT=0` when the VPS is resource-constrained.

### Packaging lane

The desktop Windows packaging lane runs on the self-hosted Windows runner.
The generated installers are staged on the VPS before release and deploy.

## Canonical flow

1. `sync-submodules.yml` detects new `main` heads for `BackEnd`, `FrontEnd`,
   and `Network`, then publishes the pinned composition on `main`.
2. `submodule-ci-gate.yml` fails immediately if any of those `main` heads is
   red, incomplete, or missing. On the VPS it also provisions the dedicated
   `BackEnd` and `FrontEnd` self-hosted runners and waits for their long CI
   jobs to finish before evaluating the gate. The submodule CI jobs themselves
   run on the VPS runners in parallel when runner capacity is available.
3. `build.yml` and `test.yml` stay available as reusable PR/manual gates.
4. `deploy-vps.yml` is the canonical mainline path: it validates and builds
   on the VPS runners, publishes release metadata, deploys, and runs
   post-deploy checks. Its Windows preflight fails fast when the desktop
   runner is offline instead of leaving a job pending.
5. `deploy/compose/e2e.sh` validates the real container path on the VPS.
6. `mirror-epitech.yml` mirrors the exact Fusion tree into the Epitech repo
   after a successful `Deploy` on `main`.

## Rules

- Do not add a second deployment path outside the VPS without documenting why
  it exists.
- Do not let a green Fusion workflow mask a red submodule `main`.
- Do not use `git submodule update --remote` in production deploy steps unless
  the target SHA is also gated by CI.
- Do not switch jobs to GitHub-hosted runners until the organization has a
  non-zero Actions budget or sufficient included minutes.
- Keep the workflow surface small: one canonical deploy path, one canonical
  rollback path, plus one explicit external mirror path if it is still needed.

## Workflow inventory

### Fusion root

- `sync-submodules.yml`: canonical scheduler for publishing exact gitlinks and
  dispatching the deploy pipeline once the composition is updated.
- `submodule-ci-gate.yml`: reusable hard gate for `BackEnd`, `FrontEnd`, and
  `Network` `main` health, including VPS runner bootstrap.
- `build.yml`: reusable Linux bundle build gate for PRs and manual runs.
- `test.yml`: reusable web, Network core, Docker E2E, and P2P smoke gate for
  PRs and manual runs.
- `deploy-vps.yml`: canonical production deploy and VPS validation path. It
  also invokes the reusable build and test gates before publishing and checks
  that the required Windows packaging runner is online.
- `rollback-vps.yml`: manual recovery path only.
- `mirror-epitech.yml`: explicit external mirror path to the Epitech repo.

### Submodules

- `BackEnd/.github/workflows/ci.yml`: backend build/test lane on the VPS
  runner.
- `FrontEnd/.github/workflows/ci.yml`: frontend build/test lane on the VPS
  runner.
- `Network/.github/workflows/ci.yml`: canonical orchestrator for `Network`.
- `Network/.github/workflows/release.yml`: tag-only publication path that
  reuses `ci.yml` before publishing artifacts.

## Billing constraint

The organization is currently on the Free plan. The Actions budget is set to
`$0` with `prevent_further_usage` enabled, so GitHub-hosted jobs are rejected
before a runner is assigned once included capacity is exhausted. This is why
the active workflows target the VPS runners. The hosted-runner changes remain
an explicit future optimization, not an active dependency.

### Immediate cleanup target

The next simplification should focus on the remaining duplication between:

- `deploy-vps.yml` validation jobs and the reusable `build.yml`/`test.yml`
  gates;
- `Network/.github/workflows/ci.yml` and `release.yml`;
- the backend/frontend CI lanes and the Fusion-level gate if their checks can
  be collapsed further without losing signal.
