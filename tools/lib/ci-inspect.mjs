/** Explain infrastructure refusals even when GitHub never allocates a runner or produces logs. */
import { api, repository, publicMetadata } from './github.mjs';
import { Failure } from './process.mjs';
export function allocationDiagnostic(job, annotations) {
  if (job.conclusion !== 'failure' || job.steps?.length) return null;
  const messages = annotations
    .map((row) => row.message)
    .filter((message) => typeof message === 'string');
  const billing = messages.some((message) =>
    /recent account payments have failed|spending limit needs to be increased|billing.{0,12}plans/i.test(
      message,
    ),
  );
  return {
    job_id: job.id,
    job: job.name,
    kind: 'infrastructure',
    code: billing ? 'billing_or_spending_limit' : 'runner_not_started',
    messages,
    tests_executed: false,
    action: billing
      ? 'Review the account billing state and available included quota; retain the zero spending limit and repository visibility.'
      : 'Inspect the GitHub allocation annotations; no test ran in this job.',
  };
}
export function inspectRun(id, { request = api } = {}) {
  if (!/^[1-9][0-9]*$/.test(String(id))) throw new Failure('Provide --run ID', 2);
  const record = request(`repos/${repository}/actions/runs/${id}`);
  const jobs = [];
  for (let page = 1; ; page++) {
    const result = request(`repos/${repository}/actions/runs/${id}/jobs?per_page=100&page=${page}`);
    jobs.push(...result.jobs);
    if (result.jobs.length < 100) break;
  }
  const diagnostics = [];
  for (const job of jobs.filter((job) => job.conclusion === 'failure' && !job.steps?.length)) {
    const annotations = request(
      `repos/${repository}/check-runs/${job.id}/annotations?per_page=100`,
    );
    const diagnostic = allocationDiagnostic(job, annotations);
    if (diagnostic) diagnostics.push(diagnostic);
  }
  return {
    schema_version: 1,
    run: publicMetadata(record),
    jobs: { total_count: jobs.length, jobs },
    diagnostics,
  };
}
