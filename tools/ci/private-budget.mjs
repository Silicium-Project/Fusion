/** Private jobs rely on a fresh, organization-wide check from protected public main. */
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
import { api, repository, canonicalRepository } from '../lib/github.mjs';
import { Failure, git } from '../lib/process.mjs';

// Reserve for qualification artifacts, the detached receipt-signature envelope,
// bounded Linux/Windows installer candidates, and the public Workbench budget
// run itself. The query runs before this workflow uploads its bounded plan and
// public-suite reports; the signature envelope consumes part of the 6 MiB headroom.
export const organizationArtifactReservation = 392 * 1024 ** 2;

export const defaultProofMaxAgeMinutes = 15;
export const pushProofMaxAgeMinutes = 60;
// Only the component workflow widens the window, and only for a push to its main:
// the pull request already passed the 15 minute gate before the merge.
export function proofMaxAgeMinutes(env = process.env) {
  const asked = Number(env.SILICIUM_PROOF_MAX_AGE_MINUTES);
  return Number.isInteger(asked) &&
    asked >= defaultProofMaxAgeMinutes &&
    asked <= pushProofMaxAgeMinutes
    ? asked
    : defaultProofMaxAgeMinutes;
}
export function requireBudgetProof(
  record,
  jobs,
  expectedSourceSha,
  now = Date.now(),
  maxAgeMinutes = defaultProofMaxAgeMinutes,
) {
  const requiredJobs = jobs.filter((job) => job.name === 'ci/required');
  const required =
    requiredJobs.length === 1 &&
    requiredJobs[0].status === 'completed' &&
    requiredJobs[0].conclusion === 'success';
  const budget = jobs.find((job) => job.name === 'budget');
  const step = budget?.steps?.find((item) => item.name === 'Check organization artifact headroom');
  const completed = Date.parse(step?.completed_at);
  if (!/^[a-f0-9]{40}$/.test(expectedSourceSha ?? ''))
    throw new Failure('Exact Workbench policy SHA is required for the storage proof', 4);
  if (record.event !== 'push' && record.event !== 'workflow_dispatch')
    throw new Failure('Budget proof must come from trusted main', 4);
  if (
    canonicalRepository(record.head_repository?.full_name) !== repository ||
    record.head_branch !== 'main' ||
    record.head_sha !== expectedSourceSha ||
    record.path?.split('@')[0] !== '.github/workflows/ci.yml' ||
    record.conclusion !== 'success' ||
    !required ||
    budget?.conclusion !== 'success' ||
    step?.conclusion !== 'success' ||
    !Number.isFinite(completed) ||
    completed > now ||
    now - completed > maxAgeMinutes * 60_000
  )
    throw new Failure(
      'No fresh successful ci/required and organization storage check on protected Workbench main; dispatch Workbench CI on main, then retry once it succeeds',
      4,
    );
  return {
    schema_version: 1,
    repository,
    run_id: record.id,
    source_sha: record.head_sha,
    checked_at: step.completed_at,
    expires_at: new Date(completed + maxAgeMinutes * 60_000).toISOString(),
    incoming_bytes_reserved: organizationArtifactReservation,
  };
}

export function privateBudget({
  request = api,
  now = Date.now(),
  expectedSourceSha = git('rev-parse', 'HEAD'),
  maxAgeMinutes = proofMaxAgeMinutes(),
} = {}) {
  const runs = request(
    `repos/${repository}/actions/workflows/ci.yml/runs?branch=main&status=success&per_page=20`,
  ).workflow_runs;
  for (const run of runs) {
    const jobs = request(`repos/${repository}/actions/runs/${run.id}/jobs?per_page=100`).jobs;
    try {
      return requireBudgetProof(run, jobs, expectedSourceSha, now, maxAgeMinutes);
    } catch (error) {
      if (error.exitCode !== 4) throw error;
    }
  }
  throw new Failure(
    'Private CI is blocked until a fresh Workbench main storage proof succeeds. This check does not enforce an Actions billing cap; verify included usage before dispatch. No VPS fallback.',
    4,
  );
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href)
  console.log(JSON.stringify(privateBudget()));
