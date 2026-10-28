/** Fetch immutable private pins with a short-lived, read-only installation token. */
import { resolve } from 'node:path';
import { root, run, Failure } from '../lib/process.mjs';
import { registry } from '../lib/planner.mjs';
import { sourcesForSuite } from '../lib/materialization.mjs';
import {
  workspaceConfig,
  workspaceLock,
  validateWorkspace,
  workspaceStatus,
} from '../lib/workspace.mjs';

const config = workspaceConfig(),
  lock = validateWorkspace(config, workspaceLock());
if (
  process.env.GITHUB_ACTIONS !== 'true' ||
  process.env.GITHUB_REPOSITORY !== config.integration_repository ||
  process.env.GITHUB_REF !== 'refs/heads/main' ||
  process.env.SILICIUM_SOURCE_VISIBILITY !== 'private'
)
  throw new Failure('Source access is restricted to private Integration main', 3);
const before = workspaceStatus();
if (
  before.status !== 'success' ||
  before.components.some((component) => component.state !== 'absent')
)
  throw new Failure('Materialize only into a clean checkout with no component sources', 3);
const suiteId = process.env.SILICIUM_SOURCE_SUITE;
const sources = sourcesForSuite(suiteId, config, registry().suites);
const token = process.env.SILICIUM_SOURCE_TOKEN;
delete process.env.SILICIUM_SOURCE_TOKEN;
if (!token)
  throw new Failure(
    'A read-only Source Reader App installation token is required; no owner PAT or Project App credential fallback',
    3,
  );
const env = {
  GIT_CONFIG_COUNT: '1',
  GIT_CONFIG_KEY_0: 'http.https://github.com/.extraheader',
  GIT_CONFIG_VALUE_0: `AUTHORIZATION: basic ${Buffer.from(`x-access-token:${token}`).toString('base64')}`,
  GIT_TERMINAL_PROMPT: '0',
  GIT_TRACE: '0',
  GIT_CURL_VERBOSE: '0',
  GIT_TRACE_CURL: '0',
  GIT_TRACE_PACKET: '0',
  GIT_TRACE_REDACT: '1',
};
for (const id of sources) {
  const component = config.components[id];
  const path = resolve(root, component.path),
    url = `https://github.com/${component.repository}.git`;
  run(['git', 'init', '--quiet', path]);
  run(['git', '-C', path, 'remote', 'add', 'origin', url]);
  run(
    ['git', '-C', path, 'fetch', '--depth=1', '--no-tags', 'origin', lock.components[id].commit],
    { env, timeout: 120_000 },
  );
  run(['git', '-C', path, 'checkout', '--quiet', '--detach', 'FETCH_HEAD']);
  if (
    run(
      ['git', '-C', path, 'config', '--local', '--get-regexp', 'core.sshCommand|http.*extraheader'],
      { allowFailure: true },
    ).status === 0
  )
    throw new Failure('Unexpected persisted source credential', 3);
}
const status = workspaceStatus();
if (
  status.status !== 'success' ||
  status.components.some((component) =>
    sources.includes(component.id) ? component.state !== 'ready' : component.state !== 'absent',
  )
)
  throw new Failure('The fetched sources do not match this suite or its pins', 3);
console.log(JSON.stringify(status));
