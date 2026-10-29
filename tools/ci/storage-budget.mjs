/** Fail before an upload can consume the organization's temporary artifact budget. */
import { api, pages, repository } from '../lib/github.mjs';
import { Failure } from '../lib/process.mjs';
import { createPrivateKey, sign } from 'node:crypto';
export function requireCoverage(installation, org, repos) {
  if (
    installation.repository_selection !== 'all' ||
    installation.account?.login !== 'Silicium-Project' ||
    installation.suspended_at
  ) {
    throw new Failure(
      'Budget observer must be an active App installed on all organization repositories',
      3,
    );
  }
  if (
    !repos.length ||
    new Set(repos.map((repo) => repo.id)).size !== repos.length ||
    repos.some((repo) => repo.owner?.login !== 'Silicium-Project')
  )
    throw new Failure('Incomplete organization repository inventory', 3);
  if (
    Number.isInteger(org.total_private_repos) &&
    repos.filter((repo) => repo.private).length !== org.total_private_repos
  ) {
    throw new Failure('Budget token cannot see every private repository', 3);
  }
  if (
    Number.isInteger(org.public_repos) &&
    repos.filter((repo) => !repo.private).length !== org.public_repos
  ) {
    throw new Failure('Budget token cannot see every public repository', 3);
  }
}
export async function installationRecord(
  {
    id = process.env.SILICIUM_BUDGET_INSTALLATION_ID,
    client = process.env.SILICIUM_BUDGET_APP_CLIENT_ID,
    key = process.env.SILICIUM_BUDGET_APP_PRIVATE_KEY,
  } = {},
  request = fetch,
) {
  if (!/^[1-9][0-9]*$/.test(id ?? '') || !client || !key)
    throw new Failure(
      'Protected App identity is required to verify organization-wide budget coverage',
      3,
    );
  const now = Math.floor(Date.now() / 1000),
    encode = (value) => Buffer.from(JSON.stringify(value)).toString('base64url');
  const payload = `${encode({ alg: 'RS256', typ: 'JWT' })}.${encode({ iat: now - 60, exp: now + 240, iss: client })}`;
  const jwt = `${payload}.${sign('RSA-SHA256', Buffer.from(payload), createPrivateKey(key)).toString('base64url')}`;
  // App JWTs require Bearer authentication; gh's GH_TOKEN uses token authentication.
  // Keep credentials in memory, with no subprocess argument, redirect, retry or response-body log.
  let response;
  try {
    response = await request(`https://api.github.com/app/installations/${id}`, {
      headers: {
        authorization: `Bearer ${jwt}`,
        accept: 'application/vnd.github+json',
      },
      signal: AbortSignal.timeout(15_000),
      redirect: 'error',
    });
  } catch {
    throw new Failure('App installation metadata request failed; budget coverage is unknown', 3);
  }
  if (!response.ok)
    throw new Failure(`App installation metadata refused: HTTP ${response.status}`, 3);
  try {
    return await response.json();
  } catch {
    throw new Failure('Invalid App installation metadata; budget coverage is unknown', 3);
  }
}
const FREE_LIMIT = 400 * 1024 ** 2;
const ENTERPRISE_LIMIT = 512 * 1024 ** 2;
export function organizationArtifactLimit(organization, declaredMiB) {
  // Enterprise plans include substantially more Actions/Packages storage. Keep
  // this internal cap conservative during the trial, and fall back to the
  // previous Free allowance as soon as the organization reports another plan.
  if (organization?.plan?.name)
    return organization.plan.name === 'enterprise' ? ENTERPRISE_LIMIT : FREE_LIMIT;
  // An installation token may not see `plan`. A human-declared cap then applies,
  // never below the Free allowance nor above the Enterprise cap; anything else fails closed.
  if (/^[1-9][0-9]{2,3}$/.test(declaredMiB ?? '')) {
    const declared = Number(declaredMiB) * 1024 ** 2;
    if (declared >= FREE_LIMIT && declared <= ENTERPRISE_LIMIT) return declared;
  }
  return FREE_LIMIT;
}
export function remainingBudget(usage, incoming, limit = 400 * 1024 ** 2) {
  if (
    ![usage, incoming, limit].every(Number.isSafeInteger) ||
    usage < 0 ||
    incoming < 0 ||
    usage + incoming >= limit
  )
    throw new Failure(
      'Temporary artifact budget exhausted; delete transferred artifacts or wait for expiry. No VPS fallback.',
      4,
    );
  return limit - usage - incoming;
}
if (process.argv[1]?.endsWith('/storage-budget.mjs')) {
  // An organization-scoped read token is required: a repository token cannot prove org usage.
  const repos = pages('orgs/Silicium-Project/repos?type=all');
  const organization = api('orgs/Silicium-Project');
  if (process.env.GITHUB_ACTIONS === 'true')
    requireCoverage(await installationRecord(), organization, repos);
  else
    requireCoverage(
      { repository_selection: 'all', account: { login: 'Silicium-Project' } },
      organization,
      repos,
    );
  let usage = 0;
  for (const repo of repos) {
    for (let page = 1; ; page++) {
      const rows = api(
        `repos/${repo.full_name}/actions/artifacts?per_page=100&page=${page}`,
      ).artifacts;
      usage += rows.filter((x) => !x.expired).reduce((n, x) => n + x.size_in_bytes, 0);
      if (rows.length < 100) break;
    }
  }
  const incoming = Number(process.env.SILICIUM_INCOMING_BYTES ?? 64 * 1024 ** 2);
  const limit = organizationArtifactLimit(
    organization,
    process.env.SILICIUM_ORG_ARTIFACT_LIMIT_MIB,
  );
  console.log(
    JSON.stringify({
      schema_version: 1,
      repository,
      repositories_observed: repos.length,
      plan_observed: organization?.plan?.name ?? null,
      usage_bytes: usage,
      incoming_bytes: incoming,
      limit_bytes: limit,
      remaining_bytes: remainingBudget(usage, incoming, limit),
    }),
  );
}
