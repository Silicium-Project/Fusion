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
const deliveryArtifactLimits = Object.freeze({
  api: 48 * 1024 ** 2,
  web: 40 * 1024 ** 2,
  network: 112 * 1024 ** 2,
  node_ui: 2 * 1024 ** 2,
});
const deliveryArtifactNames = Object.freeze({
  api: 'delivery-api',
  web: 'delivery-web',
  network: 'delivery-network',
  node_ui: 'delivery-node-ui',
});
const deliveryArchiveOverheadBytes = 256 * 1024;
const maxDeliveryArtifactBytes =
  Object.values(deliveryArtifactLimits).reduce((sum, bytes) => sum + bytes, 0) +
  Object.keys(deliveryArtifactLimits).length * deliveryArchiveOverheadBytes;

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

export function validatePrivateDeliveryArtifacts(artifacts, runAttempt) {
  const attempt = Number(runAttempt);
  if (!Number.isSafeInteger(attempt) || attempt < 1)
    throw new Failure('A positive Integration run attempt is required');
  if (!Array.isArray(artifacts) || artifacts.length > 100)
    throw new Failure('Could not inspect the complete Integration artifact list');
  const expected = new Map(
    Object.entries(deliveryArtifactNames).map(([suite, base]) => [
      `${base}-${attempt}`,
      { suite, limit: deliveryArtifactLimits[suite] },
    ]),
  );
  const selected = artifacts.filter((artifact) => expected.has(artifact?.name));
  if (
    selected.length !== expected.size ||
    new Set(selected.map((x) => x.name)).size !== expected.size
  )
    throw new Failure(
      'Every deliverable suite must upload exactly one artifact for this run attempt',
    );
  let total = 0;
  const validated = selected
    .map((artifact) => {
      const requirement = expected.get(artifact.name);
      const size = artifact.size_in_bytes;
      if (
        !Number.isSafeInteger(artifact.id) ||
        artifact.id < 1 ||
        artifact.expired !== false ||
        !Number.isSafeInteger(size) ||
        size < 1 ||
        size > requirement.limit + deliveryArchiveOverheadBytes ||
        !/^sha256:[a-f0-9]{64}$/.test(artifact.digest ?? '')
      )
        throw new Failure(`Invalid, expired, oversized, or unhashed ${requirement.suite} artifact`);
      total += size;
      return {
        suite: requirement.suite,
        id: artifact.id,
        name: artifact.name,
        digest: artifact.digest,
        size_bytes: size,
      };
    })
    .sort((a, b) => a.suite.localeCompare(b.suite));
  if (total > maxDeliveryArtifactBytes)
    throw new Failure('Private delivery artifacts exceed their combined size reservation');
  return validated;
}

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
  policySourceCompareStatus,
  plan,
  reports,
  planDigest,
  reportDigests,
  deliveryArtifacts,
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
  if (
    ![run.actor?.login, run.triggering_actor?.login].every(
      (login) => typeof login === 'string' && login.trim().length > 0,
    )
  )
    throw new Failure('The run actor and triggering actor identities must both be present');
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
    !['ahead', 'identical'].includes(policyCompareStatus) ||
    !['ahead', 'identical'].includes(policySourceCompareStatus)
  )
    throw new Failure(
      'The pinned Workbench policy must be on main and included in the qualified Workbench source commit',
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

  const validatedDeliveryArtifacts = validatePrivateDeliveryArtifacts(
    deliveryArtifacts,
    run.run_attempt,
  );

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
      delivery: validatedDeliveryArtifacts,
    },
    gate: { status: 'success', required_suites: requiredSuites },
  };
}
