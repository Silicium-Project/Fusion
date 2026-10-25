import test from 'node:test';
import assert from 'node:assert/strict';
import { qualificationEvidence } from '../../tools/ci/qualification-evidence.mjs';
const sha = 'a'.repeat(40);
const record = { id: 123, event: 'push', head_branch: 'main', conclusion: 'success', head_sha: sha,
  head_repository: { full_name: 'Silicium-Project/Fusion' } };
const plan = { schema_version: 1, source_sha: sha, dirty: false, policy_digest: 'policy', suites: ['unit'] };
const report = { schema_version: 1, source_sha: sha, dirty: false, policy_digest: 'policy', suite: 'unit',
  status: 'success', steps: [{ kind: 'test', exit_code: 0, tests_executed: 1 }] };
test('durable evidence embeds the gate inputs and exact qualified commit', () => {
  const evidence = qualificationEvidence(record, plan, [report]);
  assert.equal(evidence.gate.status, 'success');
  assert.equal(evidence.source_sha, sha);
  assert.equal(evidence.reports[0].steps[0].tests_executed, 1);
});
test('a missing, stale or skipped suite cannot become durable qualification', () => {
  for (const reports of [[], [{ ...report, source_sha: 'b'.repeat(40) }], [{ ...report, status: 'skipped' }]]) {
    assert.throws(() => qualificationEvidence(record, plan, reports));
  }
  assert.throws(() => qualificationEvidence({ ...record, event: 'pull_request' }, plan, [report]));
});
