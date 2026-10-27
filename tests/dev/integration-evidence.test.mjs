import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { privateIntegrationEvidence } from '../../tools/lib/integration-evidence.mjs';
import { registry } from '../../tools/lib/planner.mjs';
import { workspaceConfig, workspaceLock } from '../../tools/lib/workspace.mjs';

const workbenchSha = 'a'.repeat(40);
const integrationSha = 'b'.repeat(40);
const policySha = 'c'.repeat(40);
const workspace = workspaceConfig();
const lock = workspaceLock();
const lanes = registry();
const suites = Object.entries(lanes.suites)
  .filter(([, suite]) => suite.tier === 'pr')
  .map(([id]) => id)
  .sort();
const policyDigest = createHash('sha256').update(JSON.stringify(lanes)).digest('hex');
const requirements = Object.fromEntries(
  suites.map((suite) => [
    suite,
    lanes.suites[suite].steps.map((step) => ({
      command: step.command,
      cwd: step.cwd ?? '.',
      kind: step.kind,
      env: step.env ?? {},
    })),
  ]),
);
const plan = {
  schema_version: 1,
  source_sha: workbenchSha,
  scope: 'integration',
  dirty: false,
  policy_digest: policyDigest,
  source_components: lock.components,
  suites,
  requirements,
};
const reports = suites.map((suite) => ({
  schema_version: 1,
  source_sha: workbenchSha,
  scope: 'integration',
  dirty: false,
  dirty_after: false,
  policy_digest: policyDigest,
  source_components: lock.components,
  suite,
  status: 'success',
  steps: requirements[suite].map((step) => ({
    ...step,
    exit_code: 0,
    ...(step.kind === 'test' ? { tests_executed: 1 } : {}),
  })),
}));
const reportDigests = suites.map((suite) => ({ suite, sha256: 'd'.repeat(64) }));
const deliveryArtifacts = [
  ['api', 'delivery-api-1'],
  ['web', 'delivery-web-1'],
  ['network', 'delivery-network-1'],
  ['node_ui', 'delivery-node-ui-1'],
].map(([suite, name], index) => ({
  id: index + 101,
  name,
  expired: false,
  size_in_bytes: 1024,
  digest: `sha256:${String(index + 1).repeat(64)}`,
}));
const run = {
  id: 741852,
  run_attempt: 1,
  status: 'in_progress',
  event: 'workflow_dispatch',
  head_branch: 'main',
  head_sha: integrationSha,
  created_at: new Date().toISOString(),
  path: '.github/workflows/qualification.yml@refs/heads/main',
  repository: { full_name: 'Silicium-Project/Integration', private: true },
  head_repository: { full_name: 'Silicium-Project/Integration' },
  actor: { login: 'maintainer' },
  triggering_actor: { login: 'maintainer' },
  html_url: 'https://github.com/Silicium-Project/Integration/actions/runs/741852',
  referenced_workflows: [
    {
      path: `Silicium-Project/Workbench/.github/workflows/private-integration-evidence.yml@${policySha}`,
      sha: policySha,
    },
  ],
};
const base = () => ({
  run,
  integrationRepositoryRecord: { full_name: 'Silicium-Project/Integration', private: true },
  workbenchRepositoryRecord: { full_name: 'Silicium-Project/Workbench', private: false },
  actorPermissions: ['write'],
  jobs: [{ name: 'integration/required', status: 'completed', conclusion: 'success' }],
  referencedWorkflows: run.referenced_workflows,
  expectedRunId: run.id,
  expectedRunAttempt: 1,
  expectedIntegrationSha: integrationSha,
  workbenchSha,
  workbenchCompareStatus: 'identical',
  policyCompareStatus: 'identical',
  policySourceCompareStatus: 'ahead',
  plan,
  reports,
  planDigest: 'e'.repeat(64),
  reportDigests,
  deliveryArtifacts,
  workspace,
  lock,
  lanes,
});

test('private evidence binds a complete main run to Workbench policy and all exact pins', () => {
  const receipt = privateIntegrationEvidence(base());
  assert.equal(receipt.status, 'success');
  assert.equal(receipt.integration.run_id, run.id);
  assert.equal(receipt.integration.commit, integrationSha);
  assert.equal(receipt.workbench.source_sha, workbenchSha);
  assert.equal(receipt.workbench.policy_workflow_sha, policySha);
  assert.deepEqual(receipt.workbench.required_suites, suites);
  assert.equal(Object.keys(receipt.workbench.component_pins).length, 5);
  assert.deepEqual(
    receipt.artifacts.reports.map((entry) => entry.suite),
    suites,
  );
  assert.deepEqual(
    receipt.artifacts.delivery.map((entry) => entry.suite),
    ['api', 'network', 'node_ui', 'web'],
  );
  assert.equal(receipt.artifacts.delivery[0].digest, deliveryArtifacts[0].digest);
});

test('public, pull-request, stale, skipped, or partial evidence fails closed', () => {
  const cases = [
    [(input) => (input.integrationRepositoryRecord.private = false)],
    [(input) => (input.run.event = 'pull_request')],
    [(input) => (input.run.head_branch = 'feature')],
    [(input) => (input.run.head_sha = 'f'.repeat(40))],
    [(input) => (input.run.actor = null)],
    [(input) => (input.run.triggering_actor = null)],
    [(input) => (input.jobs[0].conclusion = 'skipped')],
    [(input) => (input.reports = input.reports.slice(1))],
    [(input) => (input.plan.suites = input.plan.suites.slice(1))],
    [(input) => (input.plan.source_components = {})],
    [(input) => (input.workbenchCompareStatus = 'behind')],
    [(input) => (input.policyCompareStatus = 'behind')],
    [(input) => (input.policySourceCompareStatus = 'behind')],
    [(input) => (input.actorPermissions = ['read'])],
  ];
  for (const [mutate] of cases) {
    const input = structuredClone(base());
    mutate(input);
    assert.throws(() => privateIntegrationEvidence(input));
  }
});

test('workflow references, policy digests, suite reports, and artifact digests are exact', () => {
  for (const mutate of [
    (input) => (input.referencedWorkflows = []),
    (input) => (input.plan.policy_digest = 'bad'),
    (input) => (input.reports[0].source_sha = 'f'.repeat(40)),
    (input) => (input.reportDigests[0].sha256 = 'not-a-digest'),
    (input) => (input.planDigest = 'not-a-digest'),
  ]) {
    const input = structuredClone(base());
    mutate(input);
    assert.throws(() => privateIntegrationEvidence(input));
  }
});

test('private delivery outputs must be exact-attempt, bounded, live, and hashed', () => {
  for (const mutate of [
    (input) => input.deliveryArtifacts.pop(),
    (input) => (input.deliveryArtifacts[0].name = 'delivery-api-2'),
    (input) => (input.deliveryArtifacts[1].expired = true),
    (input) => (input.deliveryArtifacts[2].digest = ''),
    (input) => (input.deliveryArtifacts[3].size_in_bytes = 2 * 1024 ** 2 + 256 * 1024 + 1),
  ]) {
    const input = structuredClone(base());
    mutate(input);
    assert.throws(() => privateIntegrationEvidence(input), /artifact|attempt|deliverable/i);
  }
  const boundedArchiveOverhead = structuredClone(base());
  boundedArchiveOverhead.deliveryArtifacts[0].size_in_bytes = 48 * 1024 ** 2 + 256 * 1024;
  assert.doesNotThrow(() => privateIntegrationEvidence(boundedArchiveOverhead));
});

test('the private evidence receipt is retained under its exact workflow attempt', () => {
  const workflow = readFileSync(
    new URL('../../.github/workflows/private-integration-evidence.yml', import.meta.url),
    'utf8',
  );
  assert.match(workflow, /name: private-integration-evidence-\$\{\{ github\.run_attempt \}\}/);
});

test('qualification evidence expires after 24 hours', () => {
  const input = structuredClone(base());
  input.run.created_at = new Date(Date.now() - 24 * 60 * 60 * 1000 - 1).toISOString();
  assert.throws(() => privateIntegrationEvidence(input), /last 24 hours/);
});
