import test from 'node:test';
import assert from 'node:assert/strict';
import {
  collectArtifactPages,
  distribution,
  summarizeRuns,
  cacheMetrics,
  fitsReportDownloadBudget,
  MAX_REPORT_DOWNLOAD_BYTES,
} from '../../tools/lib/metrics.mjs';
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
test('cache report downloads have a cumulative size bound and reject invalid sizes', () => {
  assert.equal(fitsReportDownloadBudget(0, MAX_REPORT_DOWNLOAD_BYTES), true);
  assert.equal(fitsReportDownloadBudget(MAX_REPORT_DOWNLOAD_BYTES - 1, 1), true);
  assert.equal(fitsReportDownloadBudget(MAX_REPORT_DOWNLOAD_BYTES, 1), false);
  assert.equal(fitsReportDownloadBudget(-1, 1), false);
  assert.equal(fitsReportDownloadBudget(0, Number.MAX_SAFE_INTEGER), false);
  assert.equal(fitsReportDownloadBudget(0, 1, Number.NaN), false);
});
test('artifact pagination reads every page and reports a complete byte inventory', () => {
  const requested = [];
  const result = collectArtifactPages((page) => {
    requested.push(page);
    return page === 1
      ? { total_count: 102, artifacts: Array.from({ length: 100 }, (_, index) => index) }
      : { total_count: 102, artifacts: [100, 101] };
  });
  assert.deepEqual(requested, [1, 2]);
  assert.equal(result.items.length, 102);
  assert.equal(result.total, 102);
  assert.equal(result.complete, true);
  assert.equal(result.pages, 2);
});
test('artifact pagination fails closed when counts change or the page bound is reached', () => {
  const changed = collectArtifactPages((page) =>
    page === 1
      ? { total_count: 102, artifacts: Array.from({ length: 100 }, (_, index) => index) }
      : { total_count: 103, artifacts: [100, 101, 102] },
  );
  assert.equal(changed.complete, false);
  assert.equal(changed.total, null);
  assert.equal(changed.items.length, 103);
  const bounded = collectArtifactPages(
    () => ({ total_count: 500, artifacts: Array.from({ length: 100 }, (_, index) => index) }),
    { maxPages: 2 },
  );
  assert.equal(bounded.complete, false);
  assert.equal(bounded.pages, 2);
  assert.equal(bounded.items.length, 200);
  const missingTotal = collectArtifactPages(
    (page) => ({ artifacts: page === 1 ? ['a', 'b'] : [] }),
    { pageSize: 2 },
  );
  assert.equal(missingTotal.complete, false);
  assert.equal(missingTotal.items.length, 2);
});
test('cancellations, failures, quick feedback and queue time are measured independently', () => {
  const run = {
    id: 1,
    status: 'completed',
    conclusion: 'failure',
    created_at: '2026-10-25T00:00:00Z',
    run_started_at: '2026-10-25T00:00:03Z',
    updated_at: '2026-10-25T00:03:00Z',
  };
  const job = {
    name: 'quick (docs, ubuntu-24.04, 10)',
    created_at: '2026-10-25T00:00:03Z',
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
  assert.equal(result.workflow_start_wait.median_seconds, 3);
  assert.equal(result.quick_feedback.median_seconds, 60);
  assert.equal(result.job_queue_and_matrix_wait.median_seconds, 7);
  assert.equal(result.job_execution.median_seconds, 50);
});
test('workflow start delay is measured separately from job queue and test execution', () => {
  const run = {
    status: 'completed',
    conclusion: 'success',
    created_at: '2026-10-25T00:00:00Z',
    run_started_at: '2026-10-25T00:10:00Z',
    updated_at: '2026-10-25T00:11:00Z',
  };
  const job = {
    name: 'quick (docs)',
    created_at: '2026-10-25T00:10:00Z',
    status: 'completed',
    conclusion: 'success',
    started_at: '2026-10-25T00:10:03Z',
    completed_at: '2026-10-25T00:11:00Z',
    steps: [{ started_at: '2026-10-25T00:10:05Z' }],
  };
  const result = summarizeRuns([{ run, jobs: [job] }]);
  assert.equal(result.schema_version, 2);
  assert.equal(result.workflow_start_wait.median_seconds, 600);
  assert.equal(result.job_queue_and_matrix_wait.median_seconds, 5);
  assert.equal(result.job_execution.median_seconds, 55);
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
  assert.equal(summarizeRuns([{ run, jobs: [job] }]).workflow_start_wait.samples, 0);
});
test('queue metrics require job creation timestamps rather than treating runner setup as all waiting', () => {
  const run = {
    status: 'completed',
    conclusion: 'success',
    created_at: '2026-10-25T00:00:00Z',
    updated_at: '2026-10-25T00:03:00Z',
  };
  const job = {
    conclusion: 'success',
    name: 'validation',
    started_at: '2026-10-25T00:02:00Z',
    completed_at: '2026-10-25T00:03:00Z',
    steps: [{ started_at: '2026-10-25T00:02:01Z' }],
  };
  assert.equal(summarizeRuns([{ run, jobs: [job] }]).job_queue_and_matrix_wait.samples, 0);
  assert.equal(
    summarizeRuns([{ run, jobs: [{ ...job, created_at: run.created_at }] }])
      .job_queue_and_matrix_wait.median_seconds,
    121,
  );
});
