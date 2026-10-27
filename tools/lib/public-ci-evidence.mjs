import { appendFileSync } from 'node:fs';

const API_URL =
  'https://api.github.com/repos/Silicium-Project/Workbench/commits/main/check-runs?filter=latest&per_page=100';
const EXPECTED_REPOSITORY = 'Silicium-Project/Workbench';
const EXPECTED_CHECK = 'ci/required';
const EXPECTED_APP = 'github-actions';
const SHA_PATTERN = /^[a-f0-9]{40}$/;

function failure(sourceSha, code, message) {
  return {
    schema_version: 1,
    operation: 'ci.public-workbench-qualification',
    status: 'blocked',
    repository: EXPECTED_REPOSITORY,
    ref: 'refs/heads/main',
    source_sha: SHA_PATTERN.test(sourceSha ?? '') ? sourceSha : null,
    check_name: EXPECTED_CHECK,
    check_run_id: null,
    check_status: null,
    conclusion: null,
    app_slug: null,
    api_timestamp: null,
    error: { code, message },
  };
}

function hasNextPage(value) {
  return (value ?? '').split(',').some((part) => /rel="next"/.test(part));
}

export async function verifyPublicWorkbenchQualification({
  workbenchSha,
  fetchImpl = globalThis.fetch,
} = {}) {
  if (!SHA_PATTERN.test(workbenchSha ?? ''))
    return failure(
      workbenchSha,
      'invalid_workbench_sha',
      'Provide the complete Workbench main commit SHA',
    );
  let response;
  try {
    response = await fetchImpl(API_URL, {
      method: 'GET',
      redirect: 'error',
      headers: {
        accept: 'application/vnd.github+json',
        'x-github-api-version': '2026-03-10',
      },
      signal: AbortSignal.timeout(10_000),
    });
  } catch (error) {
    return failure(
      workbenchSha,
      error?.name === 'TimeoutError' ? 'public_ci_timeout' : 'public_ci_unavailable',
      'GitHub public qualification evidence could not be read',
    );
  }
  if (!response.ok)
    return failure(
      workbenchSha,
      'public_ci_http_error',
      `GitHub returned HTTP ${response.status} while reading public qualification evidence`,
    );

  const rawTimestamp = response.headers?.get('date') ?? null;
  if (!rawTimestamp || !Number.isFinite(Date.parse(rawTimestamp)))
    return failure(
      workbenchSha,
      'public_ci_timestamp_missing',
      'GitHub omitted the timestamp for public qualification evidence',
    );
  if (hasNextPage(response.headers?.get('link')))
    return failure(
      workbenchSha,
      'public_ci_pagination_incomplete',
      'GitHub returned paginated public qualification evidence',
    );

  let payload;
  try {
    payload = await response.json();
  } catch {
    return failure(
      workbenchSha,
      'public_ci_invalid_json',
      'GitHub returned invalid public qualification evidence',
    );
  }
  if (
    !Number.isSafeInteger(payload?.total_count) ||
    !Array.isArray(payload?.check_runs) ||
    payload.total_count !== payload.check_runs.length
  )
    return failure(
      workbenchSha,
      'public_ci_pagination_incomplete',
      'GitHub returned an incomplete public check-run list',
    );

  const required = payload.check_runs.filter((check) => check?.name === EXPECTED_CHECK);
  if (required.length !== 1)
    return failure(
      workbenchSha,
      required.length ? 'public_ci_ambiguous' : 'public_ci_missing',
      required.length
        ? 'GitHub returned multiple current ci/required checks'
        : 'The current Workbench main commit has no ci/required check',
    );

  const [check] = required;
  if (check.head_sha !== workbenchSha)
    return failure(
      workbenchSha,
      'public_ci_stale',
      'The current Workbench main check does not match the requested source SHA',
    );
  if (
    check.status !== 'completed' ||
    check.conclusion !== 'success' ||
    check.app?.slug !== EXPECTED_APP ||
    !Number.isSafeInteger(check.id) ||
    check.id < 1
  )
    return failure(
      workbenchSha,
      'public_ci_failed',
      'The current Workbench ci/required check is incomplete or unsuccessful',
    );

  return {
    schema_version: 1,
    operation: 'ci.public-workbench-qualification',
    status: 'success',
    repository: EXPECTED_REPOSITORY,
    ref: 'refs/heads/main',
    source_sha: workbenchSha,
    check_name: EXPECTED_CHECK,
    check_run_id: check.id,
    check_status: check.status,
    conclusion: check.conclusion,
    app_slug: check.app.slug,
    api_timestamp: new Date(Date.parse(rawTimestamp)).toISOString(),
    error: null,
  };
}

export function writePublicQualificationOutputs(result, outputPath) {
  if (!outputPath) return;
  const values = {
    status: result.status,
    source_sha: result.source_sha ?? '',
    check_name: result.check_name ?? '',
    check_run_id: result.check_run_id ?? '',
    check_status: result.check_status ?? '',
    conclusion: result.conclusion ?? '',
    app_slug: result.app_slug ?? '',
    api_timestamp: result.api_timestamp ?? '',
    error_code: result.error?.code ?? '',
    error_message: result.error?.message ?? '',
  };
  const lines = Object.entries(values).map(
    ([key, value]) => `${key}=${String(value).replace(/[\r\n]/g, ' ')}`,
  );
  appendFileSync(outputPath, `${lines.join('\n')}\n`, { mode: 0o600 });
}
