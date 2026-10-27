/** Revalidate one private Integration receipt and its downloaded output bundles. */
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { appendFileSync, existsSync } from 'node:fs';
import { Failure, inside, readJson, root, run, writeJson } from '../lib/process.mjs';
import { registry } from '../lib/planner.mjs';
import { workspaceConfig, workspaceLock } from '../lib/workspace.mjs';
import { treeSize } from './artifact-size.mjs';
import { validatePrivateDeliveryEvidence } from '../lib/private-delivery.mjs';

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

function github(path, token) {
  if (!token) throw new Failure('A short-lived GitHub App token is required for evidence lookup');
  const response = run(['gh', 'api', path], { env: { GH_TOKEN: token }, allowFailure: true });
  if (response.status)
    throw new Failure(`GitHub evidence lookup failed with status ${response.status}`);
  try {
    return JSON.parse(response.stdout);
  } catch {
    throw new Failure('GitHub returned invalid evidence JSON');
  }
}

function main() {
  if (
    process.env.GITHUB_ACTIONS !== 'true' ||
    process.env.GITHUB_REPOSITORY !== repository ||
    process.env.GITHUB_REF !== 'refs/heads/main'
  )
    throw new Failure('Private Integration outputs can be opened only by Workbench main delivery');
  const runId = required('QUALIFICATION_RUN_ID', /^[1-9][0-9]{0,18}$/);
  const attemptText = required('QUALIFICATION_ATTEMPT', /^[1-9][0-9]{0,6}$/);
  const attempt = Number(attemptText);
  const workbenchSha = required('WORKBENCH_SHA', /^[a-f0-9]{40}$/);
  if (workbenchSha !== process.env.GITHUB_SHA)
    throw new Failure('Delivery must use the exact Workbench commit qualified by Integration');
  const rootPath = inside(
    process.env.PRIVATE_DELIVERY_ARTIFACT_ROOT ?? '.artifacts/private-integration',
  );
  const receiptPath = resolve(rootPath, 'receipt/private-integration-evidence.json');
  if (!existsSync(receiptPath))
    throw new Failure('The private Integration receipt was not downloaded');

  const integrationToken = process.env.INTEGRATION_GH_TOKEN;
  const workbenchToken = process.env.WORKBENCH_GH_TOKEN;
  const integrationRepository = github(`repos/${integration}`, integrationToken);
  const workbenchRepository = github(`repos/${repository}`, workbenchToken);
  const run = github(`repos/${integration}/actions/runs/${runId}`, integrationToken);
  const jobsResponse = github(
    `repos/${integration}/actions/runs/${runId}/jobs?per_page=100`,
    integrationToken,
  );
  const artifactsResponse = github(
    `repos/${integration}/actions/runs/${runId}/artifacts?per_page=100`,
    integrationToken,
  );
  if (!Array.isArray(jobsResponse.jobs) || !Array.isArray(artifactsResponse.artifacts))
    throw new Failure('GitHub did not return complete Integration run evidence');
  const workbenchCompare = github(
    `repos/${repository}/compare/${workbenchSha}...main`,
    workbenchToken,
  );
  const policyRef = (run.referenced_workflows ?? []).find((entry) =>
    entry.path?.startsWith(
      'Silicium-Project/Workbench/.github/workflows/private-integration-evidence.yml@',
    ),
  );
  if (!policyRef?.sha)
    throw new Failure('The Integration run does not identify its Workbench policy');
  const policyCompare = github(
    `repos/${repository}/compare/${policyRef.sha}...main`,
    workbenchToken,
  );
  const receipt = readJson(receiptPath);
  const inputs = validatePrivateDeliveryEvidence({
    run,
    integrationRepository,
    workbenchRepository,
    jobs: jobsResponse.jobs,
    jobsTotalCount: jobsResponse.total_count,
    artifacts: artifactsResponse.artifacts,
    artifactsTotalCount: artifactsResponse.total_count,
    referencedWorkflows: run.referenced_workflows,
    receipt,
    expectedRunId: runId,
    expectedAttempt: attempt,
    workbenchSha,
    workbenchCompareStatus: workbenchCompare.status,
    policyCompareStatus: policyCompare.status,
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
  if (process.env.GITHUB_OUTPUT) {
    appendFileSync(
      process.env.GITHUB_OUTPUT,
      `source_sha=${workbenchSha}\nqualification_run=${runId}\nqualification_attempt=${attempt}\n`,
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
    main();
  } catch (error) {
    console.error(error.message);
    process.exitCode = error.exitCode ?? 1;
  }
