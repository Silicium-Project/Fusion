import test from 'node:test';
import assert from 'node:assert/strict';
import { distribution, summarizeRuns, cacheMetrics } from '../../tools/lib/metrics.mjs';
test('metrics retain sample counts and exclude missing or negative observations', () => {
  assert.deepEqual(distribution([]), { samples: 0, median_seconds: null, p95_seconds: null });
  assert.deepEqual(distribution([1, 2, 3, 4, -1, NaN]), {
    samples: 4,
    median_seconds: 2.5,
    p95_seconds: 4,
  });
});
test('cache evidence distinguishes disabled or missing observations from a miss', () => {
  assert.deepEqual(
    cacheMetrics([
      { cache_observations: { enabled: false } },
      {},
      { cache_observations: { enabled: true, sources: { npm: true, rust: false, go: null } } },
    ]),
    { hits: 1, misses: 1, hit_ratio: 0.5, disabled_reports: 1, unavailable_reports: 1 },
  );
  assert.equal(cacheMetrics([]).hit_ratio, null);
});
test('cancellations, failures, quick feedback and queue time are measured independently', () => {
  const run = {
    id: 1,
    status: 'completed',
    conclusion: 'failure',
    created_at: '2026-10-25T00:00:00Z',
    updated_at: '2026-10-25T00:03:00Z',
  };
  const job = {
    name: 'quick (docs, ubuntu-24.04, 10)',
    status: 'completed',
    conclusion: 'success',
    started_at: '2026-10-25T00:00:05Z',
    completed_at: '2026-10-25T00:01:00Z',
    steps: [{ started_at: '2026-10-25T00:00:10Z' }],
  };
  const result = summarizeRuns([
    { run, jobs: [job] },
    { run: { ...run, id: 2, conclusion: 'cancelled' }, jobs: [] },
  ]);
  assert.equal(result.failures, 1);
  assert.equal(result.cancellations, 1);
  assert.equal(result.failure_ratio, 1);
  assert.equal(result.quick_feedback.median_seconds, 60);
  assert.equal(result.job_queue_and_matrix_wait.median_seconds, 5);
  assert.equal(result.job_execution.median_seconds, 50);
});
test('completed jobs without timestamps do not invent quick feedback', () => {
  const run = {
    status: 'completed',
    conclusion: 'success',
    created_at: '2026-10-25T00:00:00Z',
    updated_at: '2026-10-25T00:03:00Z',
  };
  const job = {
    name: 'quick (docs)',
    status: 'completed',
    conclusion: 'success',
    completed_at: null,
  };
  assert.equal(summarizeRuns([{ run, jobs: [job] }]).quick_feedback.samples, 0);
});
