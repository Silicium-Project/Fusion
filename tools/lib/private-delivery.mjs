/** Bind a Workbench delivery input to one completed, private Integration attempt. */
import { createHash } from 'node:crypto';
import { Failure } from './process.mjs';

export const privateDeliveryArtifactPolicy = Object.freeze({
  api: { name: 'delivery-api', limit_bytes: 48 * 1024 ** 2 },
  web: { name: 'delivery-web', limit_bytes: 40 * 1024 ** 2 },
  network: { name: 'delivery-network', limit_bytes: 112 * 1024 ** 2 },
  node_ui: { name: 'delivery-node-ui', limit_bytes: 2 * 1024 ** 2 },
});
export const privateReceiptName = (attempt) => `private-integration-evidence-${attempt}`;

const sha256Pattern = /^[a-f0-9]{64}$/;
const artifactDigestPattern = /^sha256:[a-f0-9]{64}$/;
const shaPattern = /^[a-f0-9]{40}$/;
const maxRunAgeMs = 24 * 60 * 60 * 1000;
const maxReceiptBytes = 1024 ** 2;
const maxArchiveOverheadBytes = 256 * 1024;
const requiredEvidenceWorkflow =
  'Silicium-Project/Workbench/.github/workflows/private-integration-evidence.yml';
const qualificationWorkflow = '.github/workflows/qualification.yml';

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
const requiredSuites = (lanes) =>
  Object.entries(lanes?.suites ?? {})
    .filter(([, suite]) => suite.tier === 'pr')
    .map(([id]) => id)
    .sort();

function artifactForName(artifacts, name, maxSize) {
  const matches = artifacts.filter((entry) => entry.name === name);
  if (matches.length !== 1) throw new Failure(`Expected exactly one ${name} artifact`);
  const item = matches[0];
  if (
    !Number.isSafeInteger(item.id) ||
    item.id < 1 ||
    item.expired !== false ||
    !Number.isSafeInteger(item.size_in_bytes) ||
    item.size_in_bytes < 1 ||
    item.size_in_bytes > maxSize ||
    !artifactDigestPattern.test(item.digest ?? '')
  )
    throw new Failure(`Invalid, expired, oversized, or unhashed ${name} artifact`);
  return item;
}

/**
 * Validate metadata before a workflow downloads or stages any private output.
 * The caller must also use download-artifact with digest-mismatch: error.
 */
export function validatePrivateDeliveryEvidence({
  run,
  integrationRepository,
  workbenchRepository,
  jobs,
  jobsTotalCount,
  artifacts,
  artifactsTotalCount,
  referencedWorkflows,
  receipt,
  expectedRunId,
  expectedAttempt,
  workbenchSha,
  workbenchCompareStatus,
  policyCompareStatus,
  workspace,
  lock,
  lanes,
  now = Date.now(),
}) {
  const attempt = Number(expectedAttempt);
  if (!/^[1-9][0-9]*$/.test(String(expectedRunId)))
    throw new Failure('A positive Integration workflow run ID is required');
  if (!Number.isSafeInteger(attempt) || attempt < 1)
    throw new Failure('A positive Integration workflow attempt is required');
  if (!shaPattern.test(workbenchSha ?? ''))
    throw new Failure('The exact qualified Workbench source SHA is required');

  if (
    integrationRepository?.full_name !== 'Silicium-Project/Integration' ||
    integrationRepository.private !== true ||
    workbenchRepository?.full_name !== 'Silicium-Project/Workbench' ||
    workbenchRepository.private !== false
  )
    throw new Failure('The private Integration/public Workbench repository boundary changed');

  if (
    !run ||
    String(run.id) !== String(expectedRunId) ||
    Number(run.run_attempt) !== attempt ||
    !Number.isSafeInteger(run.run_number) ||
    run.run_number < 1 ||
    run.status !== 'completed' ||
    run.conclusion !== 'success' ||
    run.event !== 'workflow_dispatch' ||
    run.head_branch !== 'main' ||
    run.path?.split('@')[0] !== qualificationWorkflow ||
    run.repository?.full_name !== 'Silicium-Project/Integration' ||
    run.repository?.private !== true ||
    run.head_repository?.full_name !== 'Silicium-Project/Integration'
  )
    throw new Failure(
      'The selected run is not a successful private Integration main qualification',
    );
  const createdAt = Date.parse(run.created_at ?? '');
  if (!Number.isFinite(createdAt) || createdAt > now || now - createdAt > maxRunAgeMs)
    throw new Failure('Private qualification evidence must be less than 24 hours old');

  if (!Array.isArray(jobs) || jobsTotalCount !== jobs.length || jobs.length > 100)
    throw new Failure('The complete Integration job list could not be verified');
  const gates = jobs.filter((job) => job.name === 'integration/required');
  if (gates.length !== 1 || gates[0].status !== 'completed' || gates[0].conclusion !== 'success')
    throw new Failure('The exact Integration required gate did not succeed');

  if (
    !Array.isArray(artifacts) ||
    artifactsTotalCount !== artifacts.length ||
    artifacts.length > 100
  )
    throw new Failure('The complete Integration artifact list could not be verified');
  const artifactIds = artifacts.map((artifact) => artifact.id);
  if (
    artifactIds.some((id) => !Number.isSafeInteger(id) || id < 1) ||
    new Set(artifactIds).size !== artifactIds.length
  )
    throw new Failure('Integration returned duplicate or invalid artifact IDs');

  const references = (referencedWorkflows ?? []).filter((entry) =>
    entry.path?.startsWith(`${requiredEvidenceWorkflow}@`),
  );
  if (references.length !== 1)
    throw new Failure('The run did not use the Workbench private-evidence workflow exactly once');
  const policy = references[0];
  const policyPin = policy.path.slice(policy.path.lastIndexOf('@') + 1);
  if (
    !shaPattern.test(policy.sha ?? '') ||
    policy.sha !== policyPin ||
    !['ahead', 'identical'].includes(policyCompareStatus)
  )
    throw new Failure('The private evidence policy is not pinned to Workbench main');
  if (!['ahead', 'identical'].includes(workbenchCompareStatus))
    throw new Failure('The qualified Workbench source is not included in Workbench main');

  if (
    workspace?.repository !== 'Silicium-Project/Workbench' ||
    workspace.integration_repository !== 'Silicium-Project/Integration' ||
    lock?.schema_version !== 1 ||
    lanes?.schema_version !== 1
  )
    throw new Failure('Workbench workspace, component lock, or suite policy is invalid');

  const required = requiredSuites(lanes);
  const policyDigest = createHash('sha256').update(JSON.stringify(lanes)).digest('hex');
  if (
    receipt?.schema_version !== 1 ||
    receipt.evidence_type !== 'silicium.private-integration' ||
    receipt.status !== 'success' ||
    receipt.integration?.repository !== 'Silicium-Project/Integration' ||
    String(receipt.integration.run_id) !== String(expectedRunId) ||
    Number(receipt.integration.run_attempt) !== attempt ||
    receipt.integration.commit !== run.head_sha ||
    receipt.integration.workflow !== qualificationWorkflow ||
    receipt.workbench?.repository !== 'Silicium-Project/Workbench' ||
    receipt.workbench.source_sha !== workbenchSha ||
    receipt.workbench.policy_workflow_sha !== policy.sha ||
    receipt.workbench.policy_digest !== policyDigest ||
    !same(receipt.workbench.required_suites, required) ||
    receipt.gate?.status !== 'success' ||
    !same(receipt.gate.required_suites, required)
  )
    throw new Failure('The downloaded private evidence receipt does not match this qualification');

  const expectedPins = Object.fromEntries(
    Object.entries(lock.components)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([id, pin]) => [id, { repository: pin.repository, commit: pin.commit }]),
  );
  if (!same(receipt.workbench.component_pins, expectedPins))
    throw new Failure('The private receipt component pins differ from the qualified composition');
  if (
    !sha256Pattern.test(receipt.artifacts?.plan_sha256 ?? '') ||
    !Array.isArray(receipt.artifacts?.reports) ||
    receipt.artifacts.reports.length !== required.length ||
    !same(receipt.artifacts.reports.map((entry) => entry.suite).sort(), required) ||
    receipt.artifacts.reports.some((entry) => !sha256Pattern.test(entry.sha256 ?? ''))
  )
    throw new Failure('The private receipt does not bind every required qualification report');

  const receiptArtifact = artifactForName(
    artifacts,
    privateReceiptName(attempt),
    maxReceiptBytes + maxArchiveOverheadBytes,
  );
  const delivery = receipt.artifacts.delivery;
  if (
    !Array.isArray(delivery) ||
    delivery.length !== Object.keys(privateDeliveryArtifactPolicy).length
  )
    throw new Failure('The private receipt does not bind every delivery artifact');
  const validated = [];
  for (const [suite, requirement] of Object.entries(privateDeliveryArtifactPolicy)) {
    const name = `${requirement.name}-${attempt}`;
    const recorded = delivery.filter((entry) => entry.suite === suite);
    if (recorded.length !== 1)
      throw new Failure(`The receipt must bind exactly one ${suite} output`);
    const remote = artifactForName(
      artifacts,
      name,
      requirement.limit_bytes + maxArchiveOverheadBytes,
    );
    const entry = recorded[0];
    if (
      entry.name !== name ||
      entry.id !== remote.id ||
      entry.digest !== remote.digest ||
      entry.size_bytes !== remote.size_in_bytes
    )
      throw new Failure(`${suite} artifact identity differs from the private receipt`);
    validated.push({
      suite,
      id: remote.id,
      name,
      digest: remote.digest,
      size_bytes: remote.size_in_bytes,
      max_content_bytes: requirement.limit_bytes,
    });
  }
  const archiveBytes = validated.reduce((sum, entry) => sum + entry.size_bytes, 0);
  const archiveLimit = Object.values(privateDeliveryArtifactPolicy).reduce(
    (sum, entry) => sum + entry.limit_bytes + maxArchiveOverheadBytes,
    0,
  );
  if (archiveBytes > archiveLimit)
    throw new Failure('Private delivery artifacts exceed the reserved transfer size');

  return {
    schema_version: 1,
    status: 'verified',
    qualification: {
      repository: 'Silicium-Project/Integration',
      run_id: String(expectedRunId),
      run_attempt: attempt,
      run_number: run.run_number,
      integration_sha: run.head_sha,
      workbench_sha: workbenchSha,
      policy_workflow_sha: policy.sha,
    },
    policy_digest: policyDigest,
    component_pins: expectedPins,
    required_suites: required,
    receipt_artifact: {
      id: receiptArtifact.id,
      name: receiptArtifact.name,
      digest: receiptArtifact.digest,
      size_bytes: receiptArtifact.size_in_bytes,
    },
    artifacts: validated.sort((a, b) => a.suite.localeCompare(b.suite)),
  };
}
