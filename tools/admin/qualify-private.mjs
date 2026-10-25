/** Prepare/apply a one-commit private CI window. Does not publish or deploy anything. */
import { api, pages, repository, requireWriter } from '../lib/github.mjs';
import { git, root, writeJson, parseArgs, Failure } from '../lib/process.mjs';
import { resolve } from 'node:path';
import { requireZeroActionsBudget, privateQualificationWindow } from '../lib/billing.mjs';
import { remainingBudget, requireCoverage } from '../ci/storage-budget.mjs';
const { options: o } = parseArgs(process.argv.slice(2));
const head = o.head ?? git('rev-parse', 'HEAD');
if (git('status', '--porcelain') || head !== git('rev-parse', 'HEAD'))
  throw new Failure('Use the exact clean local commit that will be pushed', 2);
const actor = requireWriter();
if (!api(`repos/${repository}`).private)
  throw new Failure('This one-off procedure is for a private repository only', 2);
const budget = requireZeroActionsBudget(
  api('organizations/Silicium-Project/settings/billing/budgets').budgets,
);
const repos = pages('orgs/Silicium-Project/repos?type=all');
requireCoverage(
  { repository_selection: 'all', account: { login: 'Silicium-Project' } },
  api('orgs/Silicium-Project'),
  repos,
);
let usage = 0;
for (const repo of repos) {
  for (let page = 1; ; page++) {
    const artifacts = api(
      `repos/${repo.full_name}/actions/artifacts?per_page=100&page=${page}`,
    ).artifacts;
    usage += artifacts.filter((a) => !a.expired).reduce((n, a) => n + a.size_in_bytes, 0);
    if (artifacts.length < 100) break;
  }
}
remainingBudget(usage, 16 * 1024 ** 2);
const window = privateQualificationWindow(head, Number(o.minutes ?? 180));
const workflows = api(`repos/${repository}/actions/workflows?per_page=100`).workflows;
const permissions = api(`repos/${repository}/actions/permissions`);
const result = {
  schema_version: 1,
  operation: 'ci.authorize-private',
  actor: actor.login,
  status: o.apply ? 'applied' : 'planned',
  window,
  budget,
  artifact_usage_bytes: usage,
  legacy_workflows_disabled: workflows
    .filter((w) => w.path !== '.github/workflows/ci.yml')
    .map((w) => ({ id: w.id, path: w.path })),
  next: 'Push this exact SHA to the reviewed integration PR. Only qualification is permitted; delivery remains disabled.',
};
if (o.apply) {
  writeJson(resolve(root, `.artifacts/admin/private-ci-${head}.json`), {
    ...result,
    previous: { permissions, workflows },
  });
  // Retire every legacy workflow before reopening repository Actions.
  for (const workflow of workflows.filter(
    (w) => w.path !== '.github/workflows/ci.yml' && w.state === 'active',
  ))
    api(`repos/${repository}/actions/workflows/${workflow.id}/disable`, { method: 'PUT' });
  const variables = api(`repos/${repository}/actions/variables?per_page=100`).variables;
  const name = 'SILICIUM_PRIVATE_CI_WINDOW',
    body = { name, value: JSON.stringify(window) };
  if (variables.some((v) => v.name === name))
    api(`repos/${repository}/actions/variables/${name}`, { method: 'PATCH', body });
  else api(`repos/${repository}/actions/variables`, { method: 'POST', body });
  api(`repos/${repository}/actions/permissions`, {
    method: 'PUT',
    body: { enabled: true, allowed_actions: 'selected' },
  });
  api(`repos/${repository}/actions/permissions/selected-actions`, {
    method: 'PUT',
    body: {
      github_owned_allowed: true,
      verified_allowed: false,
      patterns_allowed: ['Swatinem/rust-cache@d1527c8f67ef9af357290475d4af4b0fab8f12e0'],
    },
  });
  const current = workflows.find((w) => w.path === '.github/workflows/ci.yml');
  if (current && current.state !== 'active')
    api(`repos/${repository}/actions/workflows/${current.id}/enable`, { method: 'PUT' });
}
console.log(JSON.stringify(result, null, 2));
