/** Verify the private Integration run before it can be used by delivery workflows. */
import { createHash } from 'node:crypto';
import { validateGate, requireGate } from './gate.mjs';
import { validateWorkspace } from './workspace.mjs';
import { Failure } from './process.mjs';

const integrationRepository = 'Silicium-Project/Integration';
const policyWorkflow =
  'Silicium-Project/Workbench/.github/workflows/private-integration-evidence.yml';
const qualificationWorkflow = '.github/workflows/qualification.yml';
const shaPattern = /^[a-f0-9]{40}$/;
const digestPattern = /^[a-f0-9]{64}$/;
const maxRunAgeMs = 24 * 60 * 60 * 1000;

const stable = (value) => {
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === 'object')
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, stable(value[key])]),
    );
  return value;
};
const same = (left, right) => JSON.stringify(stable(left)) === JSON.stringify(stable(right));
const trustedPermission = (permission) => ['admin', 'maintain', 'write'].includes(permission);

/**
 * Build a private, metadata-only receipt after checking GitHub's run record and
 * the exact plan/reports produced by the caller. No input here is a signature.
 */
export function privateIntegrationEvidence({
  run,
  integrationRepositoryRecord,
  workbenchRepositoryRecord,
  actorPermissions,
  jobs,
  referencedWorkflows,
  expectedRunId,
  expectedRunAttempt,
  expectedIntegrationSha,
  workbenchSha,
  workbenchCompareStatus,
  policyCompareStatus,
  plan,
  reports,
  planDigest,
  reportDigests,
  workspace,
  lock,
  lanes,
  now = Date.now(),
}) {
  if (integrationRepositoryRecord?.full_name !== integrationRepository)
    throw new Failure('The evidence run must belong to Silicium-Project/Integration');
  if (integrationRepositoryRecord.private !== true)
    throw new Failure('Private Integration execution is required');
  if (workbenchRepositoryRecord?.full_name !== 'Silicium-Project/Workbench')
    throw new Failure('The source policy must come from Silicium-Project/Workbench');
  if (workbenchRepositoryRecord.private !== false)
    throw new Failure('Workbench must remain public for the reusable policy workflow');

  if (
    !run ||
    String(run.id) !== String(expectedRunId) ||
    String(run.run_attempt) !== String(expectedRunAttempt) ||
    run.status !== 'in_progress' ||
    run.event !== 'workflow_dispatch' ||
    run.head_branch !== 'main' ||
    run.head_sha !== expectedIntegrationSha ||
    run.path?.split('@')[0] !== qualificationWorkflow ||
    run.repository?.full_name !== integrationRepository ||
    run.repository?.private !== true ||
    run.head_repository?.full_name !== integrationRepository
  )
    throw new Failure('The current run is not the trusted private Integration main qualification');
  const createdAt = Date.parse(run.created_at ?? '');
  if (!Number.isFinite(createdAt) || createdAt > now || now - createdAt > maxRunAgeMs)
    throw new Failure(
      'Private qualification evidence must come from a run started within the last 24 hours',
    );

  if (
    !Array.isArray(actorPermissions) ||
    !actorPermissions.length ||
    actorPermissions.some((p) => !trustedPermission(p))
  )
    throw new Failure('The run actor and triggering actor must have Integration write access');

  if (!Array.isArray(jobs) || jobs.length !== 1 || jobs[0].name !== 'integration/required')
    throw new Failure('The complete Integration job list must contain exactly one required gate');
  if (jobs[0].status !== 'completed' || jobs[0].conclusion !== 'success')
    throw new Failure('integration/required did not complete successfully');

  if (
    !shaPattern.test(workbenchSha ?? '') ||
    !['ahead', 'identical'].includes(workbenchCompareStatus)
  )
    throw new Failure(
      'The exact Workbench source commit must already be included in Workbench main',
    );
  if (
    workspace?.repository !== 'Silicium-Project/Workbench' ||
    workspace.integration_repository !== integrationRepository
  )
    throw new Failure(
      'Workbench repository configuration does not match the private integration contract',
    );
  validateWorkspace(workspace, lock);

  const policyReferences = (referencedWorkflows ?? []).filter((entry) =>
    entry.path?.startsWith(`${policyWorkflow}@`),
  );
  if (policyReferences.length !== 1)
    throw new Failure('The run must reference exactly one Workbench private-evidence workflow');
  const policyReference = policyReferences[0];
  const policyPin = policyReference.path.slice(policyReference.path.lastIndexOf('@') + 1);
  if (
    !shaPattern.test(policyReference.sha ?? '') ||
    policyReference.sha !== policyPin ||
    !['ahead', 'identical'].includes(policyCompareStatus)
  )
    throw new Failure(
      'The reusable Workbench workflow must be pinned to a commit already on Workbench main',
    );

  if (!lanes || lanes.schema_version !== 1 || !lanes.suites)
    throw new Failure('The pinned Workbench suite registry is invalid');
  const policyDigest = createHash('sha256').update(JSON.stringify(lanes)).digest('hex');
  const requiredSuites = Object.entries(lanes.suites)
    .filter(([, suite]) => suite.tier === 'pr')
    .map(([id]) => id)
    .sort();
  if (
    plan?.scope !== 'integration' ||
    plan.source_sha !== workbenchSha ||
    plan.policy_digest !== policyDigest ||
    !same(plan.suites, requiredSuites)
  )
    throw new Failure(
      'The private plan does not match the exact Workbench commit and complete suite policy',
    );
  if (!same(plan.source_components, lock.components))
    throw new Failure('The qualification plan does not contain every exact private component pin');

  requireGate(validateGate(plan, reports, { expectedSha: workbenchSha }));
  if (!digestPattern.test(planDigest ?? ''))
    throw new Failure('The plan artifact digest is missing');
  if (!Array.isArray(reportDigests) || reportDigests.length !== requiredSuites.length)
    throw new Failure('A digest for every required suite report is mandatory');
  const sortedDigests = [...reportDigests].sort((a, b) => a.suite.localeCompare(b.suite));
  if (
    sortedDigests.some(
      (entry, index) =>
        entry.suite !== requiredSuites[index] || !digestPattern.test(entry.sha256 ?? ''),
    )
  )
    throw new Failure('The report digests do not match the complete required suite set');

  return {
    schema_version: 1,
    evidence_type: 'silicium.private-integration',
    status: 'success',
    integration: {
      repository: integrationRepository,
      run_id: run.id,
      run_attempt: run.run_attempt,
      run_url: run.html_url,
      commit: run.head_sha,
      workflow: qualificationWorkflow,
    },
    workbench: {
      repository: workspace.repository,
      source_sha: workbenchSha,
      policy_workflow_sha: policyReference.sha,
      policy_digest: policyDigest,
      component_pins: Object.fromEntries(
        Object.entries(lock.components)
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([id, pin]) => [id, { repository: pin.repository, commit: pin.commit }]),
      ),
      required_suites: requiredSuites,
    },
    artifacts: {
      plan_sha256: planDigest,
      reports: sortedDigests,
    },
    gate: { status: 'success', required_suites: requiredSuites },
  };
}
