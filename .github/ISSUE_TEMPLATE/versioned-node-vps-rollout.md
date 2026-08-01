---
name: Versioned node and VPS rollout
about: Track per-version rollout for nodes and VPS through CI/CD
title: "[Rollout] v"
labels: deployment, ci-cd, vps
assignees: ""
---

## Objective

Deploy a specific version to VPS and node services using CI/CD, with a clear audit trail.

## Version and scope

- Target version: `vX.Y.Z`
- Deploy ref (tag/branch/SHA):
- Environment: production/staging

## Checklist

- [ ] Release tag exists and matches intended artifacts
- [ ] CI build jobs are green for the target ref
- [ ] VPS deployment workflow executed with expected ref
- [ ] VPS release marker updated at `/var/lib/silicium/releases/current.env`
- [ ] `silicium-node.service` restarted and healthy
- [ ] Compose services healthy after rollout
- [ ] Update manifest service triggered
- [ ] Post-deploy smoke checks passed

## Rollback plan

- [ ] Previous known-good deploy ref recorded
- [ ] Rollback command prepared and tested on staging

## Evidence

- Workflow run URL:
- VPS health output summary:
- Node/version report summary:

## Closure criteria

- [ ] All checklist items validated
- [ ] Rollout evidence attached
- [ ] Any incidents or follow-up issues linked