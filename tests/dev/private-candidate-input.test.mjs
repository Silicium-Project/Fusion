import test from 'node:test';
import assert from 'node:assert/strict';
import { validatePrivateCandidateInput } from '../../tools/ci/private-candidate-input.mjs';

const sha = (letter) => letter.repeat(40);
const pins = {
  api: { repository: 'Silicium-Project/BackEnd', commit: sha('a') },
  web: { repository: 'Silicium-Project/FrontEnd', commit: sha('b') },
  node: { repository: 'Silicium-Project/DesktopApp', commit: sha('c') },
  network: { repository: 'Silicium-Project/Network', commit: sha('d') },
  solana: { repository: 'Silicium-Project/Solana', commit: sha('e') },
};
const expected = {
  workbenchSha: sha('f'),
  runId: '1234',
  attempt: '2',
  runNumber: '42',
  version: '0.3.0-dev.42',
  releaseId: `dev-0.3.0-dev.42-${sha('f').slice(0, 12)}`,
  integrationSha: sha('1'),
  policyWorkflowSha: sha('2'),
  policyDigest: '3'.repeat(64),
};
const identity = {
  schema_version: 1,
  source_sha: expected.workbenchSha,
  channel: 'dev',
  version: expected.version,
  release_id: expected.releaseId,
  qualification: {
    repository: 'Silicium-Project/Integration',
    workflow: '.github/workflows/qualification.yml',
    status: 'success',
    source_sha: expected.workbenchSha,
    workbench_sha: expected.workbenchSha,
    run_id: Number(expected.runId),
    run_attempt: Number(expected.attempt),
    run_number: Number(expected.runNumber),
    integration_sha: sha('1'),
    policy_workflow_sha: sha('2'),
    policy_digest: '3'.repeat(64),
    component_pins: pins,
  },
};
const inputs = {
  changed: ['api', 'web', 'network', 'node'],
  artifacts: {
    api: 'delivery-api-2',
    web: 'delivery-web-2',
    network: 'delivery-network-2',
    node: 'delivery-node-ui-2',
  },
  component_pins: pins,
  policy_digest: '3'.repeat(64),
  previous: null,
};

test('private candidate handoff binds version, run, policy and five immutable pins', () => {
  const verified = validatePrivateCandidateInput(identity, inputs, expected);
  assert.equal(verified.status, 'verified');
  assert.equal(verified.release_id, expected.releaseId);
  assert.deepEqual(verified.component_pins, pins);
  assert.deepEqual(verified.artifacts, {
    api: 'delivery-api-2',
    web: 'delivery-web-2',
    network: 'delivery-network-2',
    node: 'delivery-node-ui-2',
  });
});

test('private candidate handoff rejects stale or modified source evidence', () => {
  assert.throws(() =>
    validatePrivateCandidateInput(identity, inputs, { ...expected, runId: '9999' }),
  );
  assert.throws(() =>
    validatePrivateCandidateInput(identity, inputs, { ...expected, workbenchSha: sha('0') }),
  );
  const stale = structuredClone(identity);
  stale.qualification.policy_workflow_sha = sha('3');
  assert.throws(() => validatePrivateCandidateInput(stale, inputs, expected));
  assert.throws(() =>
    validatePrivateCandidateInput(identity, inputs, { ...expected, policyWorkflowSha: sha('4') }),
  );
  const changedPins = structuredClone(inputs);
  changedPins.component_pins.web.commit = sha('9');
  assert.throws(() => validatePrivateCandidateInput(identity, changedPins, expected));
  const wrongArtifact = structuredClone(inputs);
  wrongArtifact.artifacts.network = 'delivery-network-1';
  assert.throws(() => validatePrivateCandidateInput(identity, wrongArtifact, expected));
});

test('private candidate handoff rejects production or a version from another run', () => {
  const production = structuredClone(identity);
  production.channel = 'prod';
  assert.throws(() => validatePrivateCandidateInput(production, inputs, expected));
  assert.throws(() =>
    validatePrivateCandidateInput(identity, inputs, { ...expected, version: '0.3.0-dev.41' }),
  );
  assert.throws(() =>
    validatePrivateCandidateInput(identity, inputs, {
      ...expected,
      releaseId: 'prod-0.3.0-dev.42-ffffffffffff',
    }),
  );
});
