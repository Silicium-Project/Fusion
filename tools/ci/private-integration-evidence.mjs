/** Validate the caller's private Integration run and write a metadata-only receipt. */
import { createHash } from 'node:crypto';
import { appendFileSync, lstatSync, readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { privateIntegrationEvidence } from '../lib/integration-evidence.mjs';
import { Failure, readJson, root, writeJson } from '../lib/process.mjs';
import { registry } from '../lib/planner.mjs';
import { workspaceConfig, workspaceLock } from '../lib/workspace.mjs';

const apiRoot = 'https://api.github.com';
const integration = 'Silicium-Project/Integration';
const workbench = 'Silicium-Project/Workbench';
const maxArtifactBytes = 16 * 1024 * 1024;
const sha256 = (bytes) => createHash('sha256').update(bytes).digest('hex');

async function github(path) {
  const token = process.env.GITHUB_TOKEN;
  if (!token) throw new Failure('GITHUB_TOKEN with caller Actions: read permission is required');
  const response = await fetch(`${apiRoot}/${path}`, {
    headers: {
      accept: 'application/vnd.github+json',
      authorization: `Bearer ${token}`,
      'x-github-api-version': '2026-03-10',
    },
    signal: AbortSignal.timeout(15_000),
  });
  if (!response.ok) throw new Failure(`GitHub evidence lookup failed with HTTP ${response.status}`);
  return response.json();
}

function regularJsonFiles(directory) {
  return readdirSync(directory, { withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith('.json'))
    .map((entry) => resolve(directory, entry.name))
    .sort();
}

async function main() {
  const runId = process.env.GITHUB_RUN_ID;
  const runAttempt = process.env.GITHUB_RUN_ATTEMPT;
  const workbenchSha = process.env.WORKBENCH_SHA;
  const currentSha = process.env.GITHUB_SHA;
  if (!/^[1-9][0-9]*$/.test(runId ?? '') || !/^[1-9][0-9]*$/.test(runAttempt ?? ''))
    throw new Failure('GitHub run ID and attempt are required');
  if (!/^[a-f0-9]{40}$/.test(workbenchSha ?? '') || !/^[a-f0-9]{40}$/.test(currentSha ?? ''))
    throw new Failure('Complete Workbench and Integration commit SHAs are required');

  const integrationRepository = await github(`repos/${integration}`);
  const workbenchRepository = await github(`repos/${workbench}`);
  const run = await github(`repos/${integration}/actions/runs/${runId}`);
  const jobsResponse = await github(`repos/${integration}/actions/runs/${runId}/jobs?per_page=100`);
  if (!Array.isArray(jobsResponse.jobs) || jobsResponse.total_count !== jobsResponse.jobs.length)
    throw new Failure('Could not inspect the complete Integration job list');
  const requiredJobs = jobsResponse.jobs.filter((job) => job.name === 'integration/required');
  const artifactResponse = await github(
    `repos/${integration}/actions/runs/${runId}/artifacts?per_page=100`,
  );
  if (
    !Array.isArray(artifactResponse.artifacts) ||
    artifactResponse.total_count !== artifactResponse.artifacts.length
  )
    throw new Failure('Could not inspect the complete Integration artifact list');
  const actors = [...new Set([run.actor?.login, run.triggering_actor?.login].filter(Boolean))];
  const actorPermissions = await Promise.all(
    actors.map(async (actor) => {
      const result = await github(
        `repos/${integration}/collaborators/${encodeURIComponent(actor)}/permission`,
      );
      return result.permission;
    }),
  );
  const workbenchCompare = await github(`repos/${workbench}/compare/${workbenchSha}...main`);
  const policyReference = (run.referenced_workflows ?? []).find((entry) =>
    entry.path?.startsWith(`${workbench}/.github/workflows/private-integration-evidence.yml@`),
  );
  if (!policyReference?.sha)
    throw new Failure('GitHub did not report the called Workbench policy SHA');
  const policyCompare = await github(`repos/${workbench}/compare/${policyReference.sha}...main`);

  const artifactsDir = resolve(root, '.artifacts');
  const planPath = resolve(artifactsDir, 'plan.json');
  const reportsDir = resolve(artifactsDir, 'reports');
  for (const path of [planPath, reportsDir]) {
    try {
      if (!lstatSync(path).isDirectory() && path !== planPath)
        throw new Failure('Invalid artifact directory');
    } catch {
      throw new Failure('Required private qualification artifacts are missing');
    }
  }
  if (!lstatSync(planPath).isFile())
    throw new Failure('The qualification plan is not a regular file');
  const reportPaths = regularJsonFiles(reportsDir);
  if (!reportPaths.length || reportPaths.length > 20)
    throw new Failure('The private run did not provide a plausible complete report set');
  const artifactBytes = [planPath, ...reportPaths].reduce((total, path) => {
    const stat = lstatSync(path);
    if (!stat.isFile()) throw new Failure('Qualification artifacts must be regular files');
    return total + stat.size;
  }, 0);
  if (artifactBytes > maxArtifactBytes)
    throw new Failure('Private qualification evidence exceeds 16 MiB');

  const planBytes = readFileSync(planPath);
  const plan = JSON.parse(planBytes.toString('utf8'));
  const reports = reportPaths.map((path) => readJson(path));
  const evidence = privateIntegrationEvidence({
    run,
    integrationRepositoryRecord: integrationRepository,
    workbenchRepositoryRecord: workbenchRepository,
    actorPermissions,
    jobs: requiredJobs,
    referencedWorkflows: run.referenced_workflows ?? [],
    expectedRunId: runId,
    expectedRunAttempt: runAttempt,
    expectedIntegrationSha: currentSha,
    workbenchSha,
    workbenchCompareStatus: workbenchCompare.status,
    policyCompareStatus: policyCompare.status,
    plan,
    reports,
    planDigest: sha256(planBytes),
    reportDigests: reportPaths.map((path, index) => ({
      suite: reports[index].suite,
      sha256: sha256(readFileSync(path)),
    })),
    deliveryArtifacts: artifactResponse.artifacts,
    workspace: workspaceConfig(root),
    lock: workspaceLock(root),
    lanes: registry(),
    now: Date.now(),
  });
  const output = resolve(artifactsDir, 'private-integration-evidence.json');
  writeJson(output, evidence);
  if (process.env.GITHUB_OUTPUT)
    appendFileSync(process.env.GITHUB_OUTPUT, `evidence=${output}\nrun_id=${runId}\n`);
  console.log(
    JSON.stringify({ status: evidence.status, run_id: runId, workbench_sha: workbenchSha }),
  );
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href)
  main().catch((error) => {
    console.error(error.message);
    process.exitCode = error.exitCode ?? 1;
  });
