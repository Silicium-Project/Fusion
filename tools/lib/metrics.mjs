/** Read-only workflow measurements. Missing observations are never counted as cache misses or zero wait. */
import { api, repository } from './github.mjs';
import { Failure, run, readJson } from './process.mjs';
import { mkdtempSync, readdirSync, rmSync } from 'node:fs';
import { resolve } from 'node:path';
import { tmpdir } from 'node:os';
export function cacheMetrics(reports) {
  let hits = 0,
    misses = 0,
    disabled = 0,
    unavailable = 0;
  for (const report of reports) {
    const cache = report.cache_observations;
    if (cache?.enabled === false) {
      disabled++;
      continue;
    }
    if (cache?.enabled !== true) {
      unavailable++;
      continue;
    }
    for (const value of Object.values(cache.sources ?? {}))
      if (value === true) hits++;
      else if (value === false) misses++;
  }
  return {
    hits,
    misses,
    hit_ratio: hits + misses ? hits / (hits + misses) : null,
    disabled_reports: disabled,
    unavailable_reports: unavailable,
  };
}
export function distribution(values) {
  const sorted = values
    .filter((value) => Number.isFinite(value) && value >= 0)
    .sort((a, b) => a - b);
  if (!sorted.length) return { samples: 0, median_seconds: null, p95_seconds: null };
  const mid = Math.floor(sorted.length / 2);
  return {
    samples: sorted.length,
    median_seconds: sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2,
    p95_seconds: sorted[Math.ceil(sorted.length * 0.95) - 1],
  };
}
function seconds(start, end) {
  const value = (Date.parse(end) - Date.parse(start)) / 1000;
  return Number.isFinite(value) && value >= 0 ? value : null;
}
export function summarizeRuns(rows) {
  const completed = rows.filter((row) => row.run.status === 'completed');
  const durations = [],
    feedback = [],
    queue = [],
    execution = [];
  let failure = 0,
    cancelled = 0,
    success = 0;
  for (const { run, jobs } of completed) {
    if (run.conclusion === 'cancelled') {
      cancelled++;
      continue;
    }
    if (run.conclusion === 'success') success++;
    else failure++;
    const duration = seconds(run.created_at, run.updated_at);
    if (duration !== null) durations.push(duration);
    const quick = jobs.filter(
      (job) => job.name.startsWith('quick (') && job.conclusion !== 'skipped',
    );
    if (quick.length && quick.every((job) => job.status === 'completed')) {
      const ended = quick.map((job) => Date.parse(job.completed_at)).filter(Number.isFinite);
      if (ended.length === quick.length) {
        const value = seconds(run.created_at, new Date(Math.max(...ended)).toISOString());
        if (value !== null) feedback.push(value);
      }
    }
    for (const job of jobs.filter((job) => job.conclusion !== 'skipped')) {
      const first = job.steps?.[0]?.started_at;
      const wait = seconds(job.started_at, first),
        work = seconds(first, job.completed_at);
      if (wait !== null) queue.push(wait);
      if (work !== null) execution.push(work);
    }
  }
  return {
    schema_version: 1,
    total_runs: rows.length,
    active_runs: rows.length - completed.length,
    successes: success,
    failures: failure,
    cancellations: cancelled,
    failure_ratio: success + failure ? failure / (success + failure) : null,
    workflow: distribution(durations),
    quick_feedback: distribution(feedback),
    job_queue_and_matrix_wait: distribution(queue),
    job_execution: distribution(execution),
    definitions: {
      quick_feedback: 'run creation to last completed quick lane',
      job_queue_and_matrix_wait:
        'job started_at to first executed step; includes matrix throttling',
      p95: 'nearest rank; always report sample count',
    },
    runs: rows.map(({ run }) => ({
      id: run.id,
      sha: run.head_sha,
      url: run.html_url,
      status: run.status,
      conclusion: run.conclusion,
    })),
  };
}
export function inspectMetrics(limit = 20) {
  if (!Number.isInteger(limit) || limit < 1 || limit > 100)
    throw new Failure('Metrics limit must fit 1..100', 2);
  const runs = api(
    `repos/${repository}/actions/workflows/ci.yml/runs?per_page=${limit}`,
  ).workflow_runs;
  const rows = runs.map((run) => ({
    run,
    jobs: api(`repos/${repository}/actions/runs/${run.id}/jobs?per_page=100`).jobs,
  }));
  const summary = summarizeRuns(rows);
  summary.artifacts = api(`repos/${repository}/actions/artifacts?per_page=100`);
  const artifacts = summary.artifacts.artifacts;
  summary.artifacts = {
    observed: artifacts.length,
    total: summary.artifacts.total_count,
    bytes: artifacts.filter((a) => !a.expired).reduce((n, a) => n + a.size_in_bytes, 0),
    complete: summary.artifacts.total_count <= 100,
    scope: repository,
  };
  const temp = mkdtempSync(resolve(tmpdir(), 'silicium-ci-metrics-'));
  const reports = [];
  let unavailable = 0;
  try {
    for (const { run: record } of rows.filter((row) => row.run.status === 'completed')) {
      const available = api(
        `repos/${repository}/actions/runs/${record.id}/artifacts?per_page=100`,
      ).artifacts.filter((a) => a.name.startsWith('report-') && !a.expired);
      if (!available.length) {
        unavailable++;
        continue;
      }
      if (available.reduce((sum, a) => sum + a.size_in_bytes, 0) > 16 * 1024 ** 2)
        throw new Failure('Metric reports exceed their bounded download size', 4);
      const folder = resolve(temp, String(record.id));
      const result = run(
        [
          'gh',
          'run',
          'download',
          String(record.id),
          '--repo',
          repository,
          '--pattern',
          'report-*',
          '--dir',
          folder,
        ],
        { allowFailure: true, timeout: 120_000 },
      );
      if (result.status) {
        unavailable++;
        continue;
      }
      for (const file of readdirSync(folder, { recursive: true }).filter((file) =>
        file.endsWith('.json'),
      ))
        reports.push(readJson(resolve(folder, file)));
    }
    summary.caches = { ...cacheMetrics(reports), runs_without_report_evidence: unavailable };
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
  return summary;
}
