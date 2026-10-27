import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { registry } from '../../tools/lib/planner.mjs';
import { workspaceConfig, workspaceLock } from '../../tools/lib/workspace.mjs';
import {
  privateDeliveryArtifactPolicy,
  privateReceiptName,
  privateReceiptSignatureName,
  validatePrivateDeliveryEvidence,
} from '../../tools/lib/private-delivery.mjs';

const sha = (character) => character.repeat(40);
const digest = (character) => character.repeat(64);
const workspace = workspaceConfig();
const lock = workspaceLock();
const lanes = registry();
const workbenchSha = sha('a');
const integrationSha = sha('b');
const policySha = sha('c');
const required = Object.entries(lanes.suites)
  .filter(([, entry]) => entry.tier === 'pr')
  .map(([id]) => id)
  .sort();
const policyDigest = createHash('sha256').update(JSON.stringify(lanes)).digest('hex');
const pins = Object.fromEntries(
  Object.entries(lock.components)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([id, pin]) => [id, { repository: pin.repository, commit: pin.commit }]),
);

function base() {
  const now = Date.now();
  const runId = '123456789';
  const attempt = 2;
  const artifactRows = Object.entries(privateDeliveryArtifactPolicy).map(
    ([suite, policy], index) => ({
      id: 100 + index,
      name: `${policy.name}-${attempt}`,
      digest: `sha256:${digest(String(index + 1))}`,
      size_in_bytes: Math.min(policy.limit_bytes, 1024 ** 2),
      expired: false,
    }),
  );
  const receiptArtifact = {
    id: 110,
    name: privateReceiptName(attempt),
    digest: `sha256:${digest('5')}`,
    size_in_bytes: 4096,
    expired: false,
  };
  const signatureArtifact = {
    id: 111,
    name: privateReceiptSignatureName(attempt),
    digest: `sha256:${digest('8')}`,
    size_in_bytes: 4096,
    expired: false,
  };
  const run = {
    id: Number(runId),
    run_attempt: attempt,
    run_number: 31,
    status: 'completed',
    conclusion: 'success',
    event: 'workflow_dispatch',
    head_branch: 'main',
    head_sha: integrationSha,
    path: '.github/workflows/qualification.yml@refs/heads/main',
    created_at: new Date(now - 60_000).toISOString(),
    repository: { full_name: 'Silicium-Project/Integration', private: true },
    head_repository: { full_name: 'Silicium-Project/Integration' },
  };
  const referencedWorkflows = [
    {
      path: `Silicium-Project/Workbench/.github/workflows/private-integration-evidence.yml@${policySha}`,
      sha: policySha,
    },
  ];
  const receipt = {
    schema_version: 1,
    evidence_type: 'silicium.private-integration',
    status: 'success',
    integration: {
      repository: 'Silicium-Project/Integration',
      run_id: Number(runId),
      run_attempt: attempt,
      commit: integrationSha,
      workflow: '.github/workflows/qualification.yml',
    },
    workbench: {
      repository: 'Silicium-Project/Workbench',
      source_sha: workbenchSha,
      policy_workflow_sha: policySha,
      policy_digest: policyDigest,
      component_pins: pins,
      required_suites: required,
    },
    artifacts: {
      plan_sha256: digest('6'),
      reports: required.map((suite) => ({ suite, sha256: digest('7') })),
      delivery: Object.entries(privateDeliveryArtifactPolicy).map(([suite, policy], index) => ({
        suite,
        id: artifactRows[index].id,
        name: artifactRows[index].name,
        digest: artifactRows[index].digest,
        size_bytes: artifactRows[index].size_in_bytes,
      })),
    },
    gate: { status: 'success', required_suites: required },
  };
  return {
    now,
    runId,
    attempt,
    workbenchSha,
    run,
    integrationRepository: { full_name: 'Silicium-Project/Integration', private: true },
    workbenchRepository: { full_name: 'Silicium-Project/Workbench', private: false },
    jobs: [
      { name: 'integration/required', status: 'completed', conclusion: 'success' },
      { name: 'evidence', status: 'completed', conclusion: 'success' },
      { name: 'integration/sign-evidence', status: 'completed', conclusion: 'success' },
    ],
    jobsTotalCount: 3,
    artifacts: [...artifactRows, receiptArtifact, signatureArtifact],
    artifactsTotalCount: artifactRows.length + 2,
    referencedWorkflows,
    receipt,
    workbenchCompareStatus: 'identical',
    policyCompareStatus: 'ahead',
    policySourceCompareStatus: 'ahead',
    workspace,
    lock,
    lanes,
  };
}

test('private delivery inputs bind one successful Integration run to its exact receipt and artifacts', () => {
  const input = base();
  const verified = validatePrivateDeliveryEvidence({
    ...input,
    expectedRunId: input.runId,
    expectedAttempt: input.attempt,
  });
  assert.equal(verified.status, 'verified');
  assert.equal(verified.qualification.integration_sha, integrationSha);
  assert.equal(verified.artifacts.length, Object.keys(privateDeliveryArtifactPolicy).length);
  assert.equal(
    verified.receipt_signature_artifact.name,
    privateReceiptSignatureName(input.attempt),
  );
});

test('public, failed, stale, mismatched, partial, or expired private inputs fail closed', () => {
  const mutations = [
    (input) => (input.integrationRepository.private = false),
    (input) => (input.run.conclusion = 'failure'),
    (input) => (input.run.head_branch = 'feature'),
    (input) => (input.run.run_attempt = 1),
    (input) => (input.run.created_at = new Date(input.now - 24 * 60 * 60 * 1000 - 1).toISOString()),
    (input) => (input.jobsTotalCount += 1),
    (input) => (input.jobs[0].conclusion = 'skipped'),
    (input) => (input.jobs[2].conclusion = 'failure'),
    (input) => input.artifacts.pop(),
    (input) => (input.artifacts[0].digest = ''),
    (input) => (input.artifacts[0].expired = true),
    (input) => (input.receipt.workbench.component_pins.api.commit = sha('f')),
    (input) => (input.receipt.workbench.source_sha = sha('f')),
    (input) => (input.workbenchCompareStatus = 'behind'),
    (input) => (input.policyCompareStatus = 'behind'),
    (input) => (input.policySourceCompareStatus = 'behind'),
    (input) => (input.referencedWorkflows = []),
  ];
  for (const mutate of mutations) {
    const input = base();
    mutate(input);
    assert.throws(() =>
      validatePrivateDeliveryEvidence({
        ...input,
        expectedRunId: input.runId,
        expectedAttempt: input.attempt,
      }),
    );
  }
});

test('receipt artifact must bind the same attempt and each remote artifact ID, digest, and size', () => {
  for (const mutate of [
    (input) => (input.receipt.artifacts.delivery[0].id += 999),
    (input) => (input.receipt.artifacts.delivery[1].digest = `sha256:${digest('f')}`),
    (input) => (input.receipt.artifacts.delivery[2].size_bytes += 1),
    (input) =>
      (input.artifacts.find((artifact) =>
        artifact.name.startsWith('private-integration-evidence-signature-'),
      ).name = 'private-integration-evidence-signature-1'),
    (input) =>
      (input.artifacts.find((artifact) =>
        artifact.name.startsWith('private-integration-evidence-signature-'),
      ).expired = true),
    (input) =>
      (input.artifacts.find((artifact) =>
        artifact.name.startsWith('private-integration-evidence-signature-'),
      ).size_in_bytes = 400 * 1024),
    (input) =>
      (input.artifacts.find((artifact) =>
        artifact.name.startsWith('private-integration-evidence-'),
      ).name = 'private-integration-evidence-1'),
  ]) {
    const input = base();
    mutate(input);
    assert.throws(() =>
      validatePrivateDeliveryEvidence({
        ...input,
        expectedRunId: input.runId,
        expectedAttempt: input.attempt,
      }),
    );
  }
});
