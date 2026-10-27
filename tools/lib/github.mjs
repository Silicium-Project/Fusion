/** GitHub API boundary: structured stdin, no shell interpolation or token persistence. */
import { run, Failure } from './process.mjs';
export const organization = 'Silicium-Project';
export const repository = 'Silicium-Project/Workbench';
export const canonicalRepository = (value) =>
  value === 'Silicium-Project/Fusion' ? repository : value;

const retryDelaysMs = [250, 750];
const isTransientReadFailure = (message) =>
  /\b(?:500|502|503|504)\b|stream error|http\/2.*(?:cancel|reset)|connection (?:reset|closed|timed out)|econnreset|etimedout|epipe|socket hang up|temporarily unavailable|temporary failure/i.test(
    message,
  );
const isGraphqlQuery = (source) =>
  typeof source === 'string' &&
  /^(?:\uFEFF)?\s*(?:#[^\n]*(?:\n|$)\s*)*(?:query(?:\s|\(|$)|\{)/i.test(source);
const waitSync = (milliseconds) => {
  Atomics.wait(
    new Int32Array(new SharedArrayBuffer(Int32Array.BYTES_PER_ELEMENT)),
    0,
    0,
    milliseconds,
  );
};

/** Create a GitHub API client; injected execution/wait functions keep retry behavior testable. */
export function createClient({ execute = run, wait = waitSync } = {}) {
  function api(path, { method = 'GET', body } = {}) {
    const args = ['gh', 'api', path, '--method', method];
    if (body !== undefined) args.push('--input', '-');
    const input = body === undefined ? undefined : JSON.stringify(body);
    // REST reads and GraphQL queries are idempotent. Never replay any mutation.
    const retryable =
      method === 'GET' || (path === 'graphql' && method === 'POST' && isGraphqlQuery(body?.query));
    let result;
    for (let attempt = 0; ; attempt++) {
      result = execute(args, { input, allowFailure: true });
      if (!result.status) break;
      const detail = `${result.error ?? ''}\n${result.stderr ?? ''}`.trim();
      if (!retryable || attempt >= retryDelaysMs.length || !isTransientReadFailure(detail))
        throw new Failure(
          `GitHub API request failed: ${(result.stderr || result.error || '').slice(-1200)}`,
          /429|rate limit/i.test(detail) ? 4 : 3,
        );
      wait(retryDelaysMs[attempt]);
    }
    return result.stdout.trim() ? JSON.parse(result.stdout) : null;
  }

  function graphql(query, variables = {}) {
    const r = api('graphql', { method: 'POST', body: { query, variables } });
    if (r.errors?.length)
      throw new Failure(`GitHub GraphQL: ${r.errors.map((x) => x.message).join('; ')}`, 3);
    return r.data;
  }

  return { api, graphql };
}

const client = createClient();
export const { api, graphql } = client;
export function pages(path) {
  const result = [];
  for (let page = 1; ; page++) {
    const values = api(`${path}${path.includes('?') ? '&' : '?'}per_page=100&page=${page}`);
    if (!Array.isArray(values)) throw new Failure('Expected GitHub collection', 3);
    result.push(...values);
    if (values.length < 100) return result;
  }
}
export function publicApi(path, { allowMissing = false } = {}) {
  const url = new URL(path, 'https://api.github.com/');
  if (url.origin !== 'https://api.github.com')
    throw new Failure('Invalid public GitHub API path', 2);
  const response = run(
    [
      'curl',
      '--silent',
      '--show-error',
      '--max-time',
      '15',
      '--header',
      'Accept: application/vnd.github+json',
      '--header',
      'X-GitHub-Api-Version: 2026-03-10',
      '--write-out',
      '\\n%{http_code}',
      url.toString(),
    ],
    { allowFailure: true },
  );
  if (response.status) throw new Failure('Public GitHub API request failed');
  const match = response.stdout.match(/\n([0-9]{3})$/);
  if (!match) throw new Failure('Public GitHub API returned an invalid response');
  const status = Number(match[1]);
  if (status === 404 && allowMissing) return null;
  if (status < 200 || status >= 300)
    throw new Failure(`Public GitHub API request failed with HTTP ${status}`);
  try {
    return JSON.parse(response.stdout.slice(0, match.index));
  } catch {
    throw new Failure('Public GitHub API returned invalid JSON');
  }
}
export function publicPages(path) {
  const result = [];
  for (let page = 1; ; page++) {
    const values = publicApi(`${path}?per_page=100&page=${page}`);
    if (!Array.isArray(values)) throw new Failure('Expected a public GitHub collection', 3);
    result.push(...values);
    if (values.length < 100) return result;
  }
}
export function issueRef(value) {
  const url = new URL(value);
  const match = url.pathname.match(
    /^\/Silicium-Project\/(Workbench|Fusion|planning-private)\/issues\/([1-9][0-9]*)$/,
  );
  if (url.protocol !== 'https:' || url.host !== 'github.com' || !match || url.search || url.hash)
    throw new Failure('Expected a Silicium Workbench/planning-private issue URL', 2);
  const repo = canonicalRepository(`${organization}/${match[1]}`);
  return { repo, number: Number(match[2]), url: `https://github.com/${repo}/issues/${match[2]}` };
}
export function requireWriter(repo = repository) {
  const viewer = api('user');
  const permission = api(
    `repos/${repo}/collaborators/${encodeURIComponent(viewer.login)}/permission`,
  );
  if (!['admin', 'maintain', 'write'].includes(permission.permission))
    throw new Failure('A maintainer write permission is required', 3);
  return viewer;
}
export function verifiedRun(id, { sha, workflow = '.github/workflows/ci.yml' } = {}) {
  if (!/^[1-9][0-9]*$/.test(String(id))) throw new Failure('Invalid workflow run ID', 2);
  const r = api(`repos/${repository}/actions/runs/${id}`);
  if (
    r.conclusion !== 'success' ||
    r.event !== 'push' ||
    r.head_branch !== 'main' ||
    canonicalRepository(r.head_repository?.full_name) !== repository ||
    (sha && r.head_sha !== sha) ||
    r.path?.split('@')[0] !== workflow
  )
    throw new Failure('Run is not a qualified main push from the expected workflow', 3);
  const jobs = api(`repos/${repository}/actions/runs/${id}/jobs?per_page=100`).jobs;
  if (
    workflow === '.github/workflows/ci.yml' &&
    !jobs.some(
      (j) => j.name === 'ci/required' && j.status === 'completed' && j.conclusion === 'success',
    )
  )
    throw new Failure('Required gate was not executed successfully', 3);
  return r;
}

export function publicMetadata(value) {
  if (Array.isArray(value)) return value.map(publicMetadata);
  if (value && typeof value === 'object')
    return Object.fromEntries(
      Object.entries(value)
        .filter(
          ([key]) =>
            !/^(temp_clone_token|access_token|refresh_token|private_key|authorization)$/i.test(key),
        )
        .map(([key, v]) => [key, publicMetadata(v)]),
    );
  return value;
}
