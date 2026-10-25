import test from 'node:test';
import assert from 'node:assert/strict';
import { validateGate } from '../../tools/lib/gate.mjs';
const sha = 'a'.repeat(40);
const plan = { schema_version: 1, source_sha: sha, policy_digest: 'policy', suites: ['unit'], dirty: false };
const report = () => ({ schema_version: 1, source_sha: sha, policy_digest: 'policy', suite: 'unit', dirty: false, status: 'success', steps: [{ kind: 'test', exit_code: 0, tests_executed: 3 }] });
test('actual successful required execution passes', () => assert.equal(validateGate(plan,[report()]).status,'success'));
for (const status of ['failure','cancelled','skipped','timed_out','running']) test(`${status} required suite is red`, () => assert.equal(validateGate(plan,[{...report(),status}]).status,'failure'));
test('missing or duplicate reports fail', () => { for (const r of [[],[report(),report()]]) assert.equal(validateGate(plan,r).status,'failure'); });
test('stale commit and policy fail', () => { for (const field of ['source_sha','policy_digest']) assert.equal(validateGate(plan,[{...report(),[field]:'other'}]).status,'failure'); });
test('zero executed tests and dirty checkouts fail', () => {
  const r=report(); r.steps[0].tests_executed=0;assert.equal(validateGate(plan,[r]).status,'failure');
  assert.equal(validateGate({...plan,dirty:true},[report()]).status,'failure');
});
test('failed commands cannot be hidden by success status', () => { const r=report();r.steps[0].exit_code=1;assert.equal(validateGate(plan,[r]).status,'failure'); });
