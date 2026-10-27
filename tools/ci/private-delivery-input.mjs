/** Revalidate one private Integration receipt and its downloaded output bundles. */
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { appendFileSync, existsSync } from 'node:fs';
import { Failure, inside, readJson, root, writeJson } from '../lib/process.mjs';
import { registry } from '../lib/planner.mjs';
import { workspaceConfig, workspaceLock } from '../lib/workspace.mjs';
import { treeSize } from './artifact-size.mjs';
import { validatePrivateDeliveryEvidence } from '../lib/private-delivery.mjs';
import { stagePrivateDelivery } from '../lib/private-delivery-stage.mjs';

const integration = 'Silicium-Project/Integration';
const repository = 'Silicium-Project/Workbench';
const suites = {
  api: 'api',
  web: 'web',
  network: 'network',
  node_ui: 'node-ui',
};

function required(name, pattern) {
  const value = process.env[name];
  if (!pattern.test(value ?? '')) throw new Failure(`Invalid or missing ${name}`, 2);
  return value;
}

async function github(path, token, { publicResource = false } = {}) {
  if (!token && !publicResource)
    throw new Failure('A short-lived GitHub Actions token is required for private evidence lookup');
  let response;
  try {
    response = await fetch(`https://api.github.com/${path}`, {
      headers: {
        accept: 'application/vnd.github+json',
        'x-github-api-version': '2026-03-10',
        ...(token ? { authorization: `Bearer ${token}` } : {}),
      },
      signal: AbortSignal.timeout(15_000),
    });
  } catch {
    throw new Failure('GitHub evidence lookup failed before receiving a response');
  }
  if (!response.ok) throw new Failure(`GitHub evidence lookup failed with HTTP ${response.status}`);
  try {
    return await response.json();
  } catch {
    throw new Failure('GitHub returned invalid evidence JSON');
  }
}

async function main() {
  if (
    process.env.GITHUB_ACTIONS !== 'true' ||
    process.env.GITHUB_REPOSITORY !== integration ||
    process.env.GITHUB_EVENT_NAME !== 'workflow_run' ||
    process.env.GITHUB_REF !== 'refs/heads/main'
  )
    throw new Failure(
      'Private delivery inputs can be opened only by the Integration main release workflow',
    );
  const runId = required('QUALIFICATION_RUN_ID', /^[1-9][0-9]{0,18}$/);
  const attemptText = required('QUALIFICATION_ATTEMPT', /^[1-9][0-9]{0,6}$/);
  const attempt = Number(attemptText);
  const workbenchSha = required('WORKBENCH_SHA', /^[a-f0-9]{40}$/);
  if (
    runId !== process.env.SOURCE_QUALIFICATION_RUN_ID ||
    attemptText !== process.env.SOURCE_QUALIFICATION_ATTEMPT
  )
    throw new Failure('Delivery inputs must identify the exact completed workflow_run event');
  const rootPath = inside(
    process.env.PRIVATE_DELIVERY_ARTIFACT_ROOT ?? '.artifacts/private-integration',
  );
  const receiptPath = resolve(rootPath, 'receipt/private-integration-evidence.json');
  if (!existsSync(receiptPath))
    throw new Failure('The private Integration receipt was not downloaded');

  const integrationToken = process.env.INTEGRATION_GH_TOKEN ?? process.env.GITHUB_TOKEN;
  const workbenchToken = process.env.WORKBENCH_GH_TOKEN;
  const integrationRepository = await github(`repos/${integration}`, integrationToken);
  const workbenchRepository = await github(`repos/${repository}`, workbenchToken, {
    publicResource: true,
  });
  const qualificationRun = await github(
    `repos/${integration}/actions/runs/${runId}`,
    integrationToken,
  );
  const jobsResponse = await github(
    `repos/${integration}/actions/runs/${runId}/jobs?per_page=100`,
    integrationToken,
  );
  const artifactsResponse = await github(
    `repos/${integration}/actions/runs/${runId}/artifacts?per_page=100`,
    integrationToken,
  );
  if (!Array.isArray(jobsResponse.jobs) || !Array.isArray(artifactsResponse.artifacts))
    throw new Failure('GitHub did not return complete Integration run evidence');
  const workbenchCompare = await github(
    `repos/${repository}/compare/${workbenchSha}...main`,
    workbenchToken,
    { publicResource: true },
  );
  const policyRef = (qualificationRun.referenced_workflows ?? []).find((entry) =>
    entry.path?.startsWith(
      'Silicium-Project/Workbench/.github/workflows/private-integration-evidence.yml@',
    ),
  );
  if (!policyRef?.sha)
    throw new Failure('The Integration run does not identify its Workbench policy');
  const policyCompare = await github(
    `repos/${repository}/compare/${policyRef.sha}...main`,
    workbenchToken,
    { publicResource: true },
  );
  const policySourceCompare = await github(
    `repos/${repository}/compare/${policyRef.sha}...${workbenchSha}`,
    workbenchToken,
    { publicResource: true },
  );
  const receipt = readJson(receiptPath);
  const inputs = validatePrivateDeliveryEvidence({
    run: qualificationRun,
    integrationRepository,
    workbenchRepository,
    jobs: jobsResponse.jobs,
    jobsTotalCount: jobsResponse.total_count,
    artifacts: artifactsResponse.artifacts,
    artifactsTotalCount: artifactsResponse.total_count,
    referencedWorkflows: qualificationRun.referenced_workflows,
    receipt,
    expectedRunId: runId,
    expectedAttempt: attempt,
    workbenchSha,
    workbenchCompareStatus: workbenchCompare.status,
    policyCompareStatus: policyCompare.status,
    policySourceCompareStatus: policySourceCompare.status,
    workspace: workspaceConfig(root),
    lock: workspaceLock(root),
    lanes: registry(),
  });

  const downloaded = [];
  for (const [suite, directory] of Object.entries(suites)) {
    const path = resolve(rootPath, directory);
    if (!existsSync(path)) throw new Failure(`The ${suite} artifact was not downloaded`);
    const size = treeSize(path);
    const artifact = inputs.artifacts.find((item) => item.suite === suite);
    if (!artifact || size < 1 || size > artifact.max_content_bytes)
      throw new Failure(`The downloaded ${suite} output violates its content-size bound`);
    downloaded.push({ suite, path: directory, size_bytes: size });
  }

  const result = { ...inputs, downloaded };
  writeJson(resolve(rootPath, 'verified-input.json'), result);
  if (process.env.STAGE_PRIVATE_DELIVERY === '1')
    result.staged = stagePrivateDelivery({
      artifactRoot: rootPath,
      workspace: root,
      artifacts: result.artifacts,
    });
  if (process.env.GITHUB_OUTPUT) {
    appendFileSync(
      process.env.GITHUB_OUTPUT,
      `source_sha=${workbenchSha}\nintegration_sha=${result.qualification.integration_sha}\n` +
        `policy_workflow_sha=${result.qualification.policy_workflow_sha}\n` +
        `policy_digest=${result.policy_digest}\nqualification_run=${runId}\nqualification_attempt=${attempt}\n`,
    );
  }
  console.log(
    JSON.stringify({
      status: result.status,
      qualification: result.qualification,
      artifacts: result.artifacts.map(({ suite, size_bytes, digest }) => ({
        suite,
        size_bytes,
        digest,
      })),
      downloaded,
    }),
  );
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href)
  try {
    await main();
  } catch (error) {
    console.error(error.message);
    process.exitCode = error.exitCode ?? 1;
  }
