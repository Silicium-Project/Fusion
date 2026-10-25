/** Apply only after the owner's exposure-report approval and the visibility change. */
import { api, repository, requireWriter } from '../lib/github.mjs';
import { Failure } from '../lib/process.mjs';
import {
  mainProtection,
  soleMaintainerRules,
  verifyMainProtection,
} from '../lib/contribution-policy.mjs';
const apply = process.argv.includes('--apply');
requireWriter();
const metadata = api(`repos/${repository}`);
if (metadata.private)
  throw new Failure(
    'Public protections require the separately approved visibility change; this command never opens a repository',
    3,
  );
if (metadata.default_branch !== 'main')
  throw new Failure('Confirm the default branch before applying main protections', 3);
const reviewers = ['Luis1454', 'Mogza'].map((login) => ({
  type: 'User',
  id: api(`users/${login}`).id,
}));
const protection = mainProtection();
const effectiveRules = api(`repos/${repository}/rules/branches/main`);
const rulesets = [
  ...new Set(effectiveRules.filter((r) => r.type === 'pull_request').map((r) => r.ruleset_id)),
].map((id) => ({
  id,
  rules: soleMaintainerRules(api(`repos/${repository}/rulesets/${id}`)),
}));
if (apply) {
  api(`repos/${repository}/branches/main/protection`, { method: 'PUT', body: protection });
  for (const { id, rules } of rulesets)
    api(`repos/${repository}/rulesets/${id}`, { method: 'PUT', body: { rules } });
  api(`repos/${repository}/actions/permissions/fork-pr-contributor-approval`, {
    method: 'PUT',
    body: { approval_policy: 'all_external_contributors' },
  });
  api(`repos/${repository}/actions/permissions/workflow`, {
    method: 'PUT',
    body: { default_workflow_permissions: 'read', can_approve_pull_request_reviews: false },
  });
  for (const name of [
    'development',
    'production',
    'signing-development',
    'signing-production',
    'windows-signing-development',
    'windows-signing-production',
    'project-automation',
    'epitech-mirror',
  ]) {
    const env = api(`repos/${repository}/environments/${name}`, {
      method: 'PUT',
      body: {
        wait_timer: 0,
        can_admins_bypass: false,
        prevent_self_review: name.includes('production'),
        reviewers: name.includes('production') ? reviewers : [],
        deployment_branch_policy: { protected_branches: false, custom_branch_policies: true },
      },
    });
    const rules = api(
      `repos/${repository}/environments/${name}/deployment-branch-policies`,
    ).branch_policies;
    if (!rules.some((r) => r.name === 'main' && r.type === 'branch'))
      api(`repos/${repository}/environments/${name}/deployment-branch-policies`, {
        method: 'POST',
        body: { name: 'main', type: 'branch' },
      });
    for (const rule of rules.filter((r) => r.name !== 'main' || r.type !== 'branch'))
      api(`repos/${repository}/environments/${name}/deployment-branch-policies/${rule.id}`, {
        method: 'DELETE',
      });
    const verified = api(`repos/${repository}/environments/${name}`);
    const review = verified.protection_rules.find((rule) => rule.type === 'required_reviewers');
    if (
      verified.can_admins_bypass !== false ||
      (name.includes('production') &&
        (!review?.prevent_self_review ||
          !review.reviewers.some((entry) => entry.reviewer.login === 'Mogza')))
    )
      throw new Failure(
        `Environment protection verification failed: ${name}; keep Actions suspended`,
      );
  }
}
const current = apply ? api(`repos/${repository}/branches/main/protection`) : null;
if (apply) verifyMainProtection(current, api(`repos/${repository}/rules/branches/main`));
console.log(
  JSON.stringify(
    {
      schema_version: 1,
      operation: 'protect-public',
      status: apply ? 'verified' : 'planned',
      contribution_mode: 'sole-maintainer',
      protection,
      rulesets,
      environments: [
        'development',
        'production',
        'signing-development',
        'signing-production',
        'windows-signing-development',
        'windows-signing-production',
        'project-automation',
        'epitech-mirror',
      ],
      actions_enabled: false,
    },
    null,
    2,
  ),
);
