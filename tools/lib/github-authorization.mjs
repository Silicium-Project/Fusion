const API_ORIGIN = 'https://api.github.com/';
const RETRYABLE_STATUSES = new Set([500, 502, 503, 504]);
const RETRY_DELAYS_MS = [250, 1000];
const REQUEST_TIMEOUT_MS = 15_000;
const MAINTAINER_PERMISSIONS = new Set(['admin', 'maintain', 'write']);

const sleep = (milliseconds) =>
  new Promise((resolve) => {
    setTimeout(resolve, milliseconds);
  });

function isTransientNetworkError(error) {
  return (
    error instanceof TypeError || error?.name === 'AbortError' || error?.name === 'TimeoutError'
  );
}

function apiUrl(path) {
  if (typeof path !== 'string' || !path || path.startsWith('//'))
    throw new Error('GitHub API path must be a non-empty relative path');
  const url = new URL(path, API_ORIGIN);
  if (url.origin !== new URL(API_ORIGIN).origin)
    throw new Error('GitHub authorization requests must stay on api.github.com');
  return url;
}

export async function githubGetJson(
  path,
  { token, fetchImpl = globalThis.fetch, sleepImpl = sleep } = {},
) {
  if (typeof token !== 'string' || !token.trim()) throw new Error('GitHub API token is required');
  if (typeof fetchImpl !== 'function')
    throw new Error('A GitHub API fetch implementation is required');
  if (typeof sleepImpl !== 'function') throw new Error('A retry delay implementation is required');

  const url = apiUrl(path);
  const maxAttempts = RETRY_DELAYS_MS.length + 1;
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    let response;
    try {
      response = await fetchImpl(url, {
        headers: {
          authorization: `Bearer ${token}`,
          accept: 'application/vnd.github+json',
        },
        signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
      });
    } catch (error) {
      if (!isTransientNetworkError(error))
        throw new Error('GitHub authorization metadata request failed before receiving a response');
      if (attempt === maxAttempts - 1)
        throw new Error(
          `GitHub authorization metadata request failed after ${maxAttempts} attempts (network or timeout)`,
        );
      await sleepImpl(RETRY_DELAYS_MS[attempt]);
      continue;
    }

    if (!response.ok) {
      if (!RETRYABLE_STATUSES.has(response.status) || attempt === maxAttempts - 1)
        throw new Error(`GitHub authorization metadata failed: HTTP ${response.status}`);
      await sleepImpl(RETRY_DELAYS_MS[attempt]);
      continue;
    }

    try {
      return await response.json();
    } catch {
      throw new Error('GitHub authorization metadata returned invalid JSON');
    }
  }

  throw new Error('GitHub authorization metadata request ended unexpectedly');
}

export async function authorizeInternalPullRequest({
  repository,
  number,
  token,
  fetchImpl = globalThis.fetch,
  sleepImpl = sleep,
}) {
  if (typeof repository !== 'string' || !/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repository))
    throw new Error('GITHUB_REPOSITORY must be an owner/repository pair');
  if (!/^[1-9][0-9]*$/.test(String(number ?? '')) || !Number.isSafeInteger(Number(number)))
    throw new Error('Missing or invalid pull request number');

  const options = { token, fetchImpl, sleepImpl };
  const pullRequest = await githubGetJson(`repos/${repository}/pulls/${number}`, options);
  const headRepositoryId = pullRequest.head?.repo?.id;
  const baseRepositoryId = pullRequest.base?.repo?.id;
  if (!Number.isSafeInteger(headRepositoryId) || headRepositoryId !== baseRepositoryId)
    throw new Error('External contributions remain disabled during stabilization');

  const login = pullRequest.user?.login;
  if (typeof login !== 'string' || !login)
    throw new Error('GitHub pull request metadata is missing the author login');

  const permission = await githubGetJson(
    `repos/${repository}/collaborators/${encodeURIComponent(login)}/permission`,
    options,
  );
  if (!MAINTAINER_PERMISSIONS.has(permission.permission))
    throw new Error('Team write permission is required for qualification');

  return {
    pull_request: Number(number),
    same_repository: true,
    permission: permission.permission,
  };
}
