/** Apply only after the owner's exposure-report approval and the visibility change. */
import { api, pages, repository, requireWriter } from '../lib/github.mjs';
import { Failure } from '../lib/process.mjs';
const apply = process.argv.includes('--apply');
requireWriter();
const metadata = api(`repos/${repository}`);
if (metadata.private)
  throw new Failure(
    'Public protections require the separately approved visibility change; this command never opens a repository',
    3,
  );
const reviewers = ['Luis1454', 'Mogza'].map((login) => ({
  type: 'User',
  id: api(`users/${login}`).id,
}));
const protection = {
  required_status_checks: { strict: true, contexts: ['ci/required'] },
  enforce_admins: true,
  required_pull_request_reviews: {
    dismiss_stale_reviews: true,
    require_code_owner_reviews: true,
    required_approving_review_count: 1,
    require_last_push_approval: true,
  },
  restrictions: null,
  required_conversation_resolution: true,
  allow_force_pushes: false,
  allow_deletions: false,
};
if (apply) {
  api(`repos/${repository}/branches/main/protection`, { method: 'PUT', body: protection });
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
  }
}
const current = apply ? api(`repos/${repository}/branches/main/protection`) : null;
if (
  apply &&
  (!current.enforce_admins?.enabled ||
    !current.required_conversation_resolution?.enabled ||
    !current.required_status_checks?.contexts?.includes('ci/required'))
)
  throw new Failure('Protection verification failed; keep Actions suspended');
console.log(
  JSON.stringify(
    {
      schema_version: 1,
      operation: 'protect-public',
      status: apply ? 'verified' : 'planned',
      protection,
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
