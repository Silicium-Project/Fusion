import test from 'node:test';
import assert from 'node:assert/strict';
import {
  mainProtection,
  soleMaintainerRules,
  verifyMainProtection,
} from '../../tools/lib/contribution-policy.mjs';

const ruleset = {
  source_type: 'Repository',
  source: 'Silicium-Project/Fusion',
  target: 'branch',
  conditions: { ref_name: { include: ['~DEFAULT_BRANCH'], exclude: [] } },
  rules: [
    { type: 'non_fast_forward' },
    { type: 'required_status_checks', parameters: { strict_required_status_checks_policy: true } },
    {
      type: 'pull_request',
      parameters: {
        required_approving_review_count: 1,
        require_code_owner_review: true,
        require_last_push_approval: true,
        require_extra_approval_for_unattributed_changes: true,
        required_reviewers: [{ reviewer: 'external' }],
        dismiss_stale_reviews_on_push: true,
        required_review_thread_resolution: true,
        allowed_merge_methods: ['merge'],
      },
    },
  ],
};
function currentProtection() {
  const planned = mainProtection();
  return {
    ...planned,
    enforce_admins: { enabled: planned.enforce_admins },
    required_conversation_resolution: { enabled: planned.required_conversation_resolution },
    allow_force_pushes: { enabled: planned.allow_force_pushes },
    allow_deletions: { enabled: planned.allow_deletions },
  };
}

test('migrating overlapping rules preserves unrelated checks, merge methods and discussions', () => {
  const before = structuredClone(ruleset);
  const rules = soleMaintainerRules(ruleset);
  assert.deepEqual(rules.slice(0, 2), ruleset.rules.slice(0, 2));
  const parameters = rules[2].parameters;
  assert.equal(parameters.required_review_thread_resolution, true);
  assert.equal(parameters.dismiss_stale_reviews_on_push, true);
  assert.deepEqual(parameters.allowed_merge_methods, ['merge']);
  assert.deepEqual(ruleset, before);
  assert.doesNotThrow(() => verifyMainProtection(currentProtection(), rules));
});

test('inherited and multi-branch rulesets cannot be relaxed by a main-only authorization', () => {
  for (const override of [
    { source_type: 'Organization' },
    { source: 'Silicium-Project/Network' },
    { target: 'tag' },
    { conditions: { ref_name: { include: ['refs/heads/main', 'refs/heads/prod'] } } },
    { conditions: { ref_name: { include: [] } } },
  ])
    assert.throws(() => soleMaintainerRules({ ...ruleset, ...override }), /shared rulesets/);
});

test('verification rejects missing PR protection, lost CI binding and weaker admin safeguards', () => {
  const current = currentProtection();
  for (const override of [
    { required_pull_request_reviews: null },
    { required_status_checks: { strict: true, checks: [{ context: 'ci/required', app_id: -1 }] } },
    { required_status_checks: { ...current.required_status_checks, strict: false } },
    { enforce_admins: { enabled: false } },
    { required_conversation_resolution: { enabled: false } },
    { allow_force_pushes: { enabled: true } },
    { allow_deletions: { enabled: true } },
  ])
    assert.throws(
      () => verifyMainProtection({ ...current, ...override }, []),
      /verification failed/,
    );
});

test('verification detects every remaining external approval gate in effective rules', () => {
  const migrated = soleMaintainerRules(ruleset)[2];
  for (const override of [
    { required_approving_review_count: 1 },
    { require_code_owner_review: true },
    { require_last_push_approval: true },
    { require_extra_approval_for_unattributed_changes: true },
    { required_reviewers: [{ reviewer: 'external' }] },
  ])
    assert.throws(
      () =>
        verifyMainProtection(currentProtection(), [
          { ...migrated, parameters: { ...migrated.parameters, ...override } },
        ]),
      /verification failed/,
    );
});
