/** Validate the metadata handoff before a private packaging job uses it. */
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { isDeepStrictEqual } from 'node:util';
import { readJson, root, Failure } from '../lib/process.mjs';

const repositories = Object.freeze({
  api: 'Silicium-Project/BackEnd',
  web: 'Silicium-Project/FrontEnd',
  node: 'Silicium-Project/DesktopApp',
  network: 'Silicium-Project/Network',
  solana: 'Silicium-Project/Solana',
});

function requireValue(value, pattern, message) {
  if (!pattern.test(String(value ?? ''))) throw new Failure(message, 4);
  return String(value);
}

export function validatePrivateCandidateInput(identity, inputs, expected) {
  const workbenchSha = requireValue(
    expected.workbenchSha,
    /^[a-f0-9]{40}$/,
    'Exact Workbench policy SHA is required',
  );
  const runId = requireValue(
    expected.runId,
    /^[1-9][0-9]{0,18}$/,
    'Qualification run ID is required',
  );
  const attempt = Number(
    requireValue(expected.attempt, /^[1-9][0-9]{0,6}$/, 'Qualification attempt is required'),
  );
  const runNumber = Number(
    requireValue(expected.runNumber, /^[1-9][0-9]{0,9}$/, 'Qualification run number is required'),
  );
  const version = requireValue(
    expected.version,
    /^\d+\.\d+\.\d+-dev\.\d+$/,
    'A development candidate version is required',
  );
  const baseVersion = readJson(resolve(root, 'tools/config/delivery.json')).base_version;
  if (version !== `${baseVersion}-dev.${runNumber}`)
    throw new Failure('Candidate version does not match the qualification run number', 4);
  const releaseId = requireValue(
    expected.releaseId,
    /^dev-\d+\.\d+\.\d+-dev\.\d+-[a-f0-9]{12}$/,
    'A development candidate ID is required',
  );
  if (!identity || !inputs || identity.schema_version !== 1)
    throw new Failure('Candidate identity or inputs are missing or unsupported', 4);
  const expectedRelease = `dev-${version}-${workbenchSha.slice(0, 12)}`;
  if (
    identity.source_sha !== workbenchSha ||
    identity.channel !== 'dev' ||
    identity.version !== version ||
    identity.release_id !== expectedRelease ||
    releaseId !== expectedRelease
  )
    throw new Failure(
      'Candidate channel, version or source differs from the approved qualification',
      4,
    );

  const qualification = identity.qualification;
  if (
    qualification?.repository !== 'Silicium-Project/Integration' ||
    qualification.workflow !== '.github/workflows/qualification.yml' ||
    qualification.status !== 'success' ||
    qualification.source_sha !== workbenchSha ||
    qualification.workbench_sha !== workbenchSha ||
    String(qualification.run_id) !== runId ||
    Number(qualification.run_attempt) !== attempt ||
    Number(qualification.run_number) !== runNumber ||
    qualification.integration_sha !== expected.integrationSha ||
    qualification.policy_workflow_sha !== expected.policyWorkflowSha ||
    qualification.policy_digest !== expected.policyDigest ||
    !/^[a-f0-9]{40}$/.test(qualification.integration_sha ?? '') ||
    !/^[a-f0-9]{40}$/.test(qualification.policy_workflow_sha ?? '') ||
    !/^[a-f0-9]{64}$/.test(qualification.policy_digest ?? '')
  )
    throw new Failure('Candidate qualification provenance is incomplete or stale', 4);

  const pins = qualification.component_pins;
  if (
    !pins ||
    Object.keys(pins).sort().join() !== Object.keys(repositories).sort().join() ||
    Object.entries(repositories).some(
      ([id, repository]) =>
        pins[id]?.repository !== repository || !/^[a-f0-9]{40}$/.test(pins[id]?.commit ?? ''),
    )
  )
    throw new Failure('Candidate does not contain the five exact private source pins', 4);

  const expectedArtifacts = {
    api: `delivery-api-${attempt}`,
    web: `delivery-web-${attempt}`,
    network: `delivery-network-${attempt}`,
    node: `delivery-node-ui-${attempt}`,
  };
  if (
    !Array.isArray(inputs.changed) ||
    inputs.changed.join() !== 'api,web,network,node' ||
    !inputs.artifacts ||
    Object.keys(inputs.artifacts).sort().join() !== Object.keys(expectedArtifacts).sort().join() ||
    Object.entries(expectedArtifacts).some(([id, name]) => inputs.artifacts[id] !== name) ||
    !isDeepStrictEqual(inputs.component_pins, pins) ||
    inputs.policy_digest !== qualification.policy_digest
  )
    throw new Failure('Candidate build inputs do not match the private qualification receipt', 4);

  return {
    schema_version: 1,
    status: 'verified',
    source_sha: workbenchSha,
    release_id: expectedRelease,
    channel: 'dev',
    version,
    qualification_run_id: runId,
    qualification_attempt: attempt,
    qualification_run_number: runNumber,
    component_pins: pins,
    artifacts: expectedArtifacts,
  };
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const candidateDirectory = resolve(root, process.argv[2] ?? '.artifacts/candidate');
  const result = validatePrivateCandidateInput(
    readJson(resolve(candidateDirectory, 'identity.json')),
    readJson(resolve(candidateDirectory, 'inputs.json')),
    {
      workbenchSha: process.env.WORKBENCH_SHA,
      runId: process.env.QUALIFICATION_RUN_ID,
      attempt: process.env.QUALIFICATION_ATTEMPT,
      runNumber: process.env.QUALIFICATION_RUN_NUMBER,
      version: process.env.RELEASE_VERSION,
      releaseId: process.env.RELEASE_ID,
      integrationSha: process.env.INTEGRATION_SHA,
      policyWorkflowSha: process.env.POLICY_WORKFLOW_SHA,
      policyDigest: process.env.POLICY_DIGEST,
    },
  );
  console.log(JSON.stringify(result));
}
