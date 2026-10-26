/** Private jobs rely on a fresh, organization-wide check from protected public main. */
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
import { api, repository, canonicalRepository } from '../lib/github.mjs';
import { Failure } from '../lib/process.mjs';

export function requireBudgetProof(record, jobs, now = Date.now()) {
  const budget = jobs.find((job) => job.name === 'budget');
  const step = budget?.steps?.find((item) => item.name === 'Check organization artifact headroom');
  const completed = Date.parse(step?.completed_at);
  if (record.event !== 'push' && record.event !== 'workflow_dispatch')
    throw new Failure('Budget proof must come from trusted main', 4);
  if (
    canonicalRepository(record.head_repository?.full_name) !== repository ||
    record.head_branch !== 'main' ||
    record.path?.split('@')[0] !== '.github/workflows/ci.yml' ||
    record.conclusion !== 'success' ||
    budget?.conclusion !== 'success' ||
    step?.conclusion !== 'success' ||
    !Number.isFinite(completed) ||
    completed > now ||
    now - completed > 15 * 60_000
  )
    throw new Failure(
      'No fresh protected-main organization storage check; dispatch Workbench CI on main, then retry once it succeeds',
      4,
    );
  return {
    schema_version: 1,
    repository,
    run_id: record.id,
    source_sha: record.head_sha,
    checked_at: step.completed_at,
    expires_at: new Date(completed + 15 * 60_000).toISOString(),
    incoming_bytes_reserved: 220200960,
  };
}

export function privateBudget({ request = api, now = Date.now() } = {}) {
  const runs = request(
    `repos/${repository}/actions/workflows/ci.yml/runs?branch=main&status=success&per_page=20`,
  ).workflow_runs;
  for (const run of runs) {
    const jobs = request(`repos/${repository}/actions/runs/${run.id}/jobs?per_page=100`).jobs;
    try {
      return requireBudgetProof(run, jobs, now);
    } catch (error) {
      if (error.exitCode !== 4) throw error;
    }
  }
  throw new Failure(
    'Private CI is blocked until a fresh Workbench main budget check succeeds. The zero-spend organization stop still applies; no VPS fallback.',
    4,
  );
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href)
  console.log(JSON.stringify(privateBudget()));
