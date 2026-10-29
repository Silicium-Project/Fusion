import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  organizationArtifactReservation,
  proofMaxAgeMinutes,
  requireBudgetProof,
  privateBudget,
} from '../../tools/ci/private-budget.mjs';
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
  { name: 'ci/required', status: 'completed', conclusion: 'success' },
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
  const proof = requireBudgetProof(record, jobs, record.head_sha, now);
  assert.equal(proof.run_id, 1);
  assert.equal(proof.incoming_bytes_reserved, organizationArtifactReservation);
  assert.equal(organizationArtifactReservation, 392 * 1024 ** 2);
  const workflow = readFileSync(new URL('../../.github/workflows/ci.yml', import.meta.url), 'utf8');
  assert.ok(workflow.includes("SILICIUM_INCOMING_BYTES: '411041792'"));
  const privateArtifacts =
    203 * 1024 ** 2 + // qualified binary archive envelope
    16 * 1024 ** 2 + // private qualification plan and reports
    1 * 1024 ** 2 + // private evidence receipt
    64 * 1024 + // detached Ed25519 signature envelope
    1 * 1024 ** 2; // candidate identity metadata
  const publicBudgetRunArtifacts = 1 * 1024 ** 2 + 4 * 1024 ** 2; // plan + four public suites
  const boundedCandidateInstallers = 120 * 1024 ** 2 + 40 * 1024 ** 2; // Linux + Windows
  assert.equal(
    organizationArtifactReservation -
      privateArtifacts -
      publicBudgetRunArtifacts -
      boundedCandidateInstallers,
    6 * 1024 ** 2 - 64 * 1024,
  );
  for (const changes of [
    { event: 'pull_request' },
    { head_branch: 'topic' },
    { head_sha: 'b'.repeat(40) },
    { conclusion: 'failure' },
    { path: '.github/workflows/other.yml' },
    { head_repository: { full_name: 'attacker/repo' } },
  ])
    assert.throws(() => requireBudgetProof({ ...record, ...changes }, jobs, record.head_sha, now));
  assert.throws(() => requireBudgetProof(record, jobs, 'short-sha', now));
  assert.throws(() => requireBudgetProof(record, [], record.head_sha, now));
  assert.throws(() => requireBudgetProof(record, [jobs[1]], record.head_sha, now));
  assert.throws(() =>
    requireBudgetProof(
      record,
      [
        jobs[0],
        { ...jobs[1] },
        { name: 'ci/required', status: 'completed', conclusion: 'failure' },
      ],
      record.head_sha,
      now,
    ),
  );
  assert.throws(() =>
    requireBudgetProof(record, [{ ...jobs[0], steps: [] }], record.head_sha, now),
  );
});
test('stale or future storage observations block uploads and no job is dispatched', () => {
  for (const at of [now + 16 * 60_000, now - 2 * 60_000])
    assert.throws(() => requireBudgetProof(record, jobs, record.head_sha, at));
  assert.throws(
    () =>
      privateBudget({
        request: () => ({ workflow_runs: [] }),
        now,
        expectedSourceSha: record.head_sha,
      }),
    /storage proof succeeds.*does not enforce an Actions billing cap/,
  );
});
test('a fresh budget check from a different main commit is rejected', () => {
  const oldRun = { ...record, id: 1, head_sha: 'b'.repeat(40) };
  const currentRun = { ...record, id: 2 };
  const proof = privateBudget({
    now,
    expectedSourceSha: record.head_sha,
    request: (path) => {
      if (path.includes('/workflows/ci.yml/runs?')) return { workflow_runs: [oldRun, currentRun] };
      return { jobs };
    },
  });
  assert.equal(proof.run_id, currentRun.id);
  assert.equal(proof.source_sha, record.head_sha);
});

test('only a requested window between 15 and 60 minutes widens the proof age', () => {
  assert.equal(proofMaxAgeMinutes({}), 15);
  assert.equal(proofMaxAgeMinutes({ SILICIUM_PROOF_MAX_AGE_MINUTES: '60' }), 60);
  assert.equal(proofMaxAgeMinutes({ SILICIUM_PROOF_MAX_AGE_MINUTES: '30' }), 30);
  for (const bad of ['0', '14', '61', '1440', '-5', '15.5', 'abc', ''])
    assert.equal(proofMaxAgeMinutes({ SILICIUM_PROOF_MAX_AGE_MINUTES: bad }), 15);
  const stale = now + 40 * 60_000;
  assert.throws(() => requireBudgetProof(record, jobs, record.head_sha, stale));
  assert.throws(() => requireBudgetProof(record, jobs, record.head_sha, stale, 15));
  assert.equal(requireBudgetProof(record, jobs, record.head_sha, stale, 60).run_id, 1);
  assert.throws(() => requireBudgetProof(record, jobs, record.head_sha, now + 62 * 60_000, 60));
  const workflow = readFileSync(
    new URL('../../.github/workflows/component-ci.yml', import.meta.url),
    'utf8',
  );
  assert.match(
    workflow,
    /SILICIUM_PROOF_MAX_AGE_MINUTES: \$\{\{ github\.event_name == 'push' && github\.ref == 'refs\/heads\/main' && '60' \|\| '15' \}\}/,
  );
});
