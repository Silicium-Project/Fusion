/**
 * Move every component's workbench-component-ci.yml to one Workbench main SHA.
 * Dry run by default; --apply pushes a branch and opens one PR per component.
 * It never merges and never touches gitlinks or components.lock.json.
 */
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { api, repository } from '../lib/github.mjs';
import { Failure, root, readJson, run } from '../lib/process.mjs';
import { privateBudget } from './private-budget.mjs';

export const workflowPath = '.github/workflows/workbench-component-ci.yml';
const sha40 = /^[a-f0-9]{40}$/;
const references = (text) => [...text.matchAll(/(?:@|policy_sha:\s*)([a-f0-9]{40})\b/g)];

/** Replace the pinned policy SHA; the workflow must name exactly one old SHA in exactly two places. */
export function repinWorkflow(text, next) {
  if (!sha40.test(next ?? '')) throw new Failure('A complete Workbench commit SHA is required', 2);
  const found = references(text);
  const olds = new Set(found.map((match) => match[1]));
  if (found.length !== 2 || olds.size !== 1)
    throw new Failure('Expected one policy SHA in `uses` and `policy_sha`; review by hand', 3);
  const [old] = olds;
  if (old === next) return { old, text, changed: false };
  return { old, text: text.split(old).join(next), changed: true };
}

export function componentRepositories(config) {
  return Object.entries(config.components).map(([id, value]) => ({
    id,
    repository: value.repository,
  }));
}

function requireTrustedPolicy(sha, check, proof) {
  const compare = check(`repos/${repository}/compare/${sha}...main`);
  if (!['ahead', 'identical'].includes(compare.status))
    throw new Failure('Policy SHA must be included in Workbench main', 3);
  // A pull request needs the 15 minute proof for this exact SHA when its CI starts.
  return proof({ expectedSourceSha: sha, maxAgeMinutes: 15 });
}

function openPullRequest({ repo, id, sha, old, execute }) {
  const branch = `lf-ci-190-repin-policy-${sha.slice(0, 8)}`;
  const directory = mkdtempSync(resolve(tmpdir(), `silicium-repin-${id}-`));
  try {
    execute(['gh', 'repo', 'clone', repo, directory, '--', '--quiet']);
    execute(['git', 'checkout', '-q', '-b', branch], { cwd: directory });
    const path = resolve(directory, workflowPath);
    writeFileSync(path, repinWorkflow(readFileSync(path, 'utf8'), sha).text);
    execute(['git', 'add', workflowPath], { cwd: directory });
    execute(['git', 'commit', '-q', '-m', `ci: pin the Workbench policy to ${sha.slice(0, 8)}`], {
      cwd: directory,
    });
    execute(['git', 'push', '-q', '-u', 'origin', branch], { cwd: directory });
    const body =
      `Passe \`workbench-component-ci.yml\` de \`${old.slice(0, 8)}\` à \`${sha.slice(0, 8)}\` ` +
      "(une ligne, deux endroits). Ne fusionner qu'après `qualify / ci/required` vert, " +
      'puis mettre à jour les pins dans Workbench.';
    const created = execute(
      [
        'gh',
        'pr',
        'create',
        '--repo',
        repo,
        '--base',
        'main',
        '--head',
        branch,
        '--title',
        `ci: pin la politique Workbench sur ${sha.slice(0, 8)}`,
        '--body',
        body,
      ],
      { cwd: directory },
    );
    return created.stdout.trim();
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
}

export function repinPolicy({
  sha,
  apply = false,
  check = api,
  proof = privateBudget,
  execute = run,
} = {}) {
  const config = readJson(resolve(root, 'tools/config/workspace.json'));
  const evidence = requireTrustedPolicy(sha, check, proof);
  const components = [];
  for (const { id, repository: repo } of componentRepositories(config)) {
    const file = check(`repos/${repo}/contents/${workflowPath}`);
    const current = repinWorkflow(Buffer.from(file.content, 'base64').toString('utf8'), sha);
    const entry = { component: id, repository: repo, from: current.old, to: sha };
    entry.changed = current.changed;
    if (apply && current.changed)
      entry.pull_request = openPullRequest({ repo, id, sha, old: current.old, execute });
    components.push(entry);
  }
  return {
    schema_version: 1,
    apply,
    policy_sha: sha,
    proof_expires_at: evidence.expires_at,
    components,
  };
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const args = process.argv.slice(2);
  const index = args.indexOf('--sha');
  const report = repinPolicy({
    sha: index >= 0 ? args[index + 1] : undefined,
    apply: args.includes('--apply'),
  });
  console.log(JSON.stringify(report, null, 2));
}
