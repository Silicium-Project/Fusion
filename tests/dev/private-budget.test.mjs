import test from 'node:test';
import assert from 'node:assert/strict';
import { requireBudgetProof, privateBudget } from '../../tools/ci/private-budget.mjs';
const now = Date.parse('2026-10-25T12:00:00Z');
const record = {
  id: 1,
  event: 'push',
  head_repository: { full_name: 'Silicium-Project/Workbench' },
  head_branch: 'main',
  head_sha: 'a'.repeat(40),
  path: '.github/workflows/ci.yml',
  conclusion: 'success',
};
const jobs = [
  {
    name: 'budget',
    conclusion: 'success',
    steps: [
      {
        name: 'Check organization artifact headroom',
        conclusion: 'success',
        completed_at: '2026-10-25T11:59:00Z',
      },
    ],
  },
];
test('private budget proof requires the actual protected organization check', () => {
  assert.equal(requireBudgetProof(record, jobs, now).run_id, 1);
  for (const changes of [
    { event: 'pull_request' },
    { head_branch: 'topic' },
    { conclusion: 'failure' },
    { path: '.github/workflows/other.yml' },
    { head_repository: { full_name: 'attacker/repo' } },
  ])
    assert.throws(() => requireBudgetProof({ ...record, ...changes }, jobs, now));
  assert.throws(() => requireBudgetProof(record, [], now));
  assert.throws(() => requireBudgetProof(record, [{ ...jobs[0], steps: [] }], now));
});
test('stale or future storage observations block uploads and no job is dispatched', () => {
  for (const at of [now + 16 * 60_000, now - 2 * 60_000])
    assert.throws(() => requireBudgetProof(record, jobs, at));
  assert.throws(() => privateBudget({ request: () => ({ workflow_runs: [] }), now }), /blocked/);
});
