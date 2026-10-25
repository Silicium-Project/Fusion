/** The required gate validates evidence for every selected lane, never an aggregate green alone. */
import { Failure } from './process.mjs';
export const stepIdentity = (step) =>
  JSON.stringify({
    command: step.command,
    cwd: step.cwd ?? '.',
    kind: step.kind,
    env: Object.fromEntries(Object.entries(step.env ?? {}).sort(([a], [b]) => a.localeCompare(b))),
  });
export function validateGate(
  plan,
  reports,
  { expectedSha = plan.source_sha, requireClean = true } = {},
) {
  const errors = [];
  if (plan.schema_version !== 1 || !/^[a-f0-9]{40}$/.test(plan.source_sha ?? ''))
    errors.push('Invalid plan identity');
  if (plan.source_sha !== expectedSha) errors.push('Plan belongs to another source commit');
  if (requireClean && plan.dirty)
    errors.push('Qualification plan was produced from a dirty checkout');
  if (
    !Array.isArray(plan.suites) ||
    !plan.suites.length ||
    new Set(plan.suites).size !== plan.suites.length
  )
    errors.push('Invalid required suite set');
  for (const suite of plan.suites ?? []) {
    const matching = reports.filter((r) => r.suite === suite);
    if (matching.length !== 1) {
      errors.push(`${suite}: expected exactly one report, got ${matching.length}`);
      continue;
    }
    const r = matching[0];
    if (
      plan.source_components &&
      JSON.stringify(r.source_components) !== JSON.stringify(plan.source_components)
    )
      errors.push(`${suite}: component revisions differ from the qualification plan`);
    if (plan.scope && r.scope !== plan.scope)
      errors.push(`${suite}: qualification scope differs from the plan`);
    const expected = plan.requirements?.[suite];
    if (!Array.isArray(expected) || !expected.length)
      errors.push(`${suite}: execution obligations missing from plan`);
    else if (
      !Array.isArray(r.steps) ||
      r.steps.length !== expected.length ||
      expected.some(
        (step, index) => !r.steps[index] || stepIdentity(step) !== stepIdentity(r.steps[index]),
      )
    )
      errors.push(`${suite}: executed commands do not match every planned obligation`);
    if (
      r.schema_version !== 1 ||
      r.source_sha !== expectedSha ||
      r.policy_digest !== plan.policy_digest
    )
      errors.push(`${suite}: stale or mismatched evidence`);
    if (requireClean && (r.dirty || r.dirty_after !== false))
      errors.push(`${suite}: dirty build or source changed during validation`);
    if (r.status !== 'success' || !r.steps?.length || r.steps.some((s) => s.exit_code !== 0))
      errors.push(`${suite}: required execution did not succeed`);
    if (
      r.steps?.some(
        (s) => s.kind === 'test' && (!Number.isInteger(s.tests_executed) || s.tests_executed < 1),
      )
    )
      errors.push(`${suite}: missing executed test count`);
  }
  return {
    schema_version: 1,
    source_sha: expectedSha,
    status: errors.length ? 'failure' : 'success',
    required_suites: plan.suites,
    errors,
  };
}
export function requireGate(result) {
  if (result.status !== 'success') throw new Failure(result.errors.join('\n'));
  return result;
}
