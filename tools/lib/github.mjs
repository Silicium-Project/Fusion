/** GitHub API boundary: structured stdin, no shell interpolation or token persistence. */
import { run, Failure } from './process.mjs';
export const organization = 'Silicium-Project';
export const repository = 'Silicium-Project/Fusion';
export function api(path, { method = 'GET', body } = {}) {
  const args = ['gh', 'api', path, '--method', method];
  if (body !== undefined) args.push('--input', '-');
  const r = run(args, {
    input: body === undefined ? undefined : JSON.stringify(body),
    allowFailure: true,
  });
  if (r.status)
    throw new Failure(
      `GitHub API request failed: ${r.stderr.slice(-1200)}`,
      /429|rate limit/i.test(r.stderr) ? 4 : 3,
    );
  return r.stdout.trim() ? JSON.parse(r.stdout) : null;
}
export function graphql(query, variables = {}) {
  const r = api('graphql', { method: 'POST', body: { query, variables } });
  if (r.errors?.length)
    throw new Failure(`GitHub GraphQL: ${r.errors.map((x) => x.message).join('; ')}`, 3);
  return r.data;
}
export function pages(path) {
  const result = [];
  for (let page = 1; ; page++) {
    const values = api(`${path}${path.includes('?') ? '&' : '?'}per_page=100&page=${page}`);
    if (!Array.isArray(values)) throw new Failure('Expected GitHub collection', 3);
    result.push(...values);
    if (values.length < 100) return result;
  }
}
export function issueRef(value) {
  const url = new URL(value);
  const match = url.pathname.match(
    /^\/Silicium-Project\/(Fusion|planning-private)\/issues\/([1-9][0-9]*)$/,
  );
  if (url.protocol !== 'https:' || url.host !== 'github.com' || !match || url.search || url.hash)
    throw new Failure('Expected a Silicium Fusion/planning-private issue URL', 2);
  return { repo: `${organization}/${match[1]}`, number: Number(match[2]), url: url.href };
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
    r.head_repository?.full_name !== repository ||
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
