# CI/CD Topology

This document describes the intended execution model for Fusion.

## Goal

Keep the workflow traceable:

- GitHub stores the source, issues, pull requests, and audit trail.
- The VPS executes the production path.
- Self-hosted runners on the VPS execute Linux CI, compilation, tests, and the
  deployment path.
- GitHub-hosted Windows capacity executes the desktop packaging lane.
- The visible lifecycle is `Build` -> `Test` -> `Deploy`.
- Every component is built on one of two explicit channels: `dev` or `prod`.

## Current contract

### GitHub

GitHub should be used as:

- source control;
- trigger surface;
- review and history;
- status display.

GitHub is not the primary compute plane for production deploy, post-deploy
validation, or the Linux CI lanes. The Windows installer is built on a
GitHub-hosted Windows runner, then staged on the VPS before publication.

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

The desktop Windows packaging lane runs on `windows-latest`.
The generated installers are staged on the VPS before release and deploy.

## Release channels

`deploy/release/channels.json` is the source of truth for the channel contract.

- `dev` is the `dev` branch, accepts prereleases, advertises `release_channel=dev`
  in the FrontEnd, BackEnd and Network metadata, and publishes a prerelease from
  `release-dev.yml`.
- `prod` is `main` (or a `v*` tag), publishes stable artifacts, and is the only
  channel allowed to execute the production VPS deployment in `deploy-vps.yml`.
- Promotion is a normal reviewed merge from `dev` to `main`; no runtime or
  update feed is switched implicitly by a development push.

The Network peer table rejects peers from the other release channel, preventing
development workers from claiming production tasks and vice versa. The
deployment roots, Compose project names, data roots, ports and systemd unit
names in the contract are separate. Dev and prod can therefore run on the same
VPS; dev is bound to the WireGuard address `10.77.0.1:8443` and does not
replace the production ingress on `80/443`. The dev web/API surface is private
to the `10.77.0.0/24` VPN and is not a public Internet endpoint.

## Canonical flow

1. `sync-submodules.yml` examines the branch selected by the channel contract
   (`dev` or `main`) in `BackEnd`, `FrontEnd`, and `Network`, resolves the
   newest commit for which every visible workflow is green, then publishes
   those exact gitlinks on the matching Fusion branch. `.gitmodules` keeps its
   production-safe `main` hint in both branches so promotion cannot rewrite the
   production tracking configuration.
2. `submodule-ci-gate.yml` uses the same resolver and selects `dev` for the
   development channel or `main` for production. A red, incomplete, or
   missing head is therefore skipped until a newer green candidate exists;
   Fusion never pins an unqualified commit. On the VPS it also provisions the
   dedicated `BackEnd` and `FrontEnd` self-hosted runners and waits for their
   long CI jobs to finish before evaluating the gate. The submodule CI jobs
   themselves run on the VPS runners in parallel when runner capacity is
   available.
3. `ci-fast.yml` is the short feedback path for pull requests and non-main
   branches. It runs only the affected web, Network core, and Silicium Node
   lanes; Docker E2E, smoke, packaging, and deployment are excluded.
4. `build.yml` and `test.yml` stay available as reusable PR/manual gates.
5. `deploy-vps.yml` is the canonical mainline path: it validates and builds
   on the VPS runners, builds Windows installers on `windows-latest`, publishes
   release metadata, deploys, and runs post-deploy checks.
6. `deploy-dev-vps.yml` is the explicit development deployment path. It pulls
   only `dev`, provisions the isolated WireGuard ingress, prepares isolated
   development configuration, deploys to `/opt/silicium-dev`, and never stops
   or rewrites production units.
7. `deploy/compose/e2e.sh` validates the real container path on the VPS.
8. `mirror-epitech.yml` mirrors the exact Fusion tree into the Epitech repo
   after a successful `Deploy` on `main`.

### Targeted iteration

`Deploy` also exposes manual validation lanes for an exact ref:

- `web`;
- `network-core`;
- `network-e2e`;
- `network-smoke`;
- `windows`;
- `linux`.

These lanes do not stage artifacts on the VPS, publish releases, or deploy.
Packaging lanes may still upload their test artifacts to the workflow for
inspection. Only `full` follows the production path. Targeted lanes use their own
cancelable concurrency group, so a new iteration does not wait behind an
active production deployment.

### Selective execution

Each repository starts with a small `changes` job. It classifies the push or
pull request by surface before creating the expensive lanes:

- FrontEnd runs unit, build, and functional tests only for application or
  dependency changes; the Nuxt output is passed from build to Playwright as an
  artifact instead of being rebuilt.
- BackEnd runs Go tests and compilation only for Go, module, database, or
  container changes.
- Network creates only the affected CodeQL, Rust-crate, workload, Python,
  Docker, P2P, and performance lanes. The workload matrix still plans every
  catalog entry when a Python/workload change is involved.
- Fusion selects the web, network, and node lanes independently. A site-only
  deployment keeps the existing node installers, while node changes alone do
  not trigger the web/network test stack.

All long-lived dependency caches are keyed by their lockfiles. Rust targets,
Go build caches, npm/pip caches, and the Linux desktop Cargo target are kept
between jobs where the runner supports it; clean-up removes stale tracked
outputs without deleting those caches.

## Rules

- Do not add a second deployment path outside the VPS without documenting why
  it exists.
- Do not let a green Fusion workflow pin a submodule SHA that has not passed all
  visible workflows; a red `main` remains pending until a newer green
  candidate exists.
- Do not use `git submodule update --remote` in production deploy steps. The
  target SHA must come from the latest-green resolver and remain pinned in
  Fusion.
- Keep the GitHub-hosted Windows job limited to desktop packaging; all
  production state changes remain on the VPS.
- Keep the workflow surface small: one canonical deploy path, one canonical
  rollback path, plus one explicit external mirror path if it is still needed.

## Workflow inventory

### Fusion root

- `sync-submodules.yml`: channel-aware scheduler for resolving the latest green
  submodule commits, publishing exact gitlinks on `dev` or `main`, and
  dispatching the deploy pipeline once the production composition is updated.
- `submodule-ci-gate.yml`: reusable latest-green gate for `BackEnd`, `FrontEnd`,
  and `Network`, including VPS runner bootstrap.
- `ci-fast.yml`: cancelable short feedback path for branch and pull-request
  iterations.
- `build.yml`: reusable Linux bundle build gate for PRs and manual runs.
- `test.yml`: reusable web, Network core, Docker E2E, and P2P smoke gate for
  PRs and manual runs.
- `deploy-vps.yml`: canonical production deploy and VPS validation path. It
  also invokes the reusable build and test gates, packages Windows installers
  on `windows-latest`, and publishes them with the VPS deployment.
- `deploy-dev-vps.yml`: guarded development deploy path using the isolated
  `/opt/silicium-dev` runtime and channel-specific ports and units.
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

## Actions capacity

The Windows packaging job uses GitHub-hosted Actions capacity. The repository
or organization must have sufficient included minutes or an enabled Actions
budget; if hosted usage is disabled, the deploy stops before packaging. Linux
validation, tests, deployment, and post-deploy checks continue to use the VPS.

### Immediate cleanup target

The next simplification should focus on the remaining duplication between:

- `deploy-vps.yml` validation jobs and the reusable `build.yml`/`test.yml`
  gates;
- `Network/.github/workflows/ci.yml` and `release.yml`;
- the backend/frontend CI lanes and the Fusion-level gate if their checks can
  be collapsed further without losing signal.
