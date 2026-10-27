/** Read-only, public audit of Workbench metadata and its active main ruleset. */
import { resolve } from 'node:path';
import { readJson, root } from './process.mjs';

const apiRoot = 'https://api.github.com';
const apiHeaders = {
  accept: 'application/vnd.github+json',
  'x-github-api-version': '2026-03-10',
};
const retryableStatuses = new Set([429, 500, 502, 503, 504]);
const retryDelays = [250, 750];

class AuditFailure extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
  }
}

function validatePolicy(policy) {
  if (
    policy?.schema_version !== 1 ||
    !/^Silicium-Project\/[A-Za-z0-9._-]+$/.test(policy.repository ?? '') ||
    !Number.isSafeInteger(policy.repository_id) ||
    policy.repository_id < 1 ||
    policy.visibility !== 'public' ||
    !/^[A-Za-z0-9._-]+$/.test(policy.default_branch ?? '') ||
    !policy.ruleset ||
    typeof policy.ruleset.name !== 'string' ||
    typeof policy.ruleset.source_type !== 'string' ||
    typeof policy.ruleset.source !== 'string' ||
    !Array.isArray(policy.ruleset.ref_name_include) ||
    !Array.isArray(policy.ruleset.ref_name_exclude) ||
    !Array.isArray(policy.ruleset.rule_types) ||
    !policy.ruleset.pull_request ||
    !Array.isArray(policy.ruleset.pull_request.allowed_merge_methods) ||
    !Array.isArray(policy.not_publicly_verifiable)
  )
    throw new AuditFailure('invalid_policy', 'Repository policy manifest is invalid');
}

function equalValue(actual, expected) {
  return JSON.stringify(actual) === JSON.stringify(expected);
}

function equalStringSet(actual, expected) {
  return (
    Array.isArray(actual) &&
    Array.isArray(expected) &&
    [...actual].sort().join('\0') === [...expected].sort().join('\0')
  );
}

function pagination(link, currentUrl) {
  const result = { next: null, last: null, present: Boolean(link) };
  if (!link) return result;
  for (const entry of link.split(/,(?=\s*<)/)) {
    const target = entry.match(/<([^>]+)>/)?.[1];
    const rel = entry.match(/\brel="?([^";]+)"?/)?.[1]?.split(/\s+/) ?? [];
    const relation = rel.find((value) => value === 'next' || value === 'last');
    if (!relation) continue;
    if (!target)
      throw new AuditFailure('invalid_pagination', 'GitHub API pagination link is invalid');
    let parsed;
    try {
      parsed = new URL(target, currentUrl);
    } catch {
      throw new AuditFailure('invalid_pagination', 'GitHub API pagination link is invalid');
    }
    if (parsed.origin !== apiRoot)
      throw new AuditFailure('invalid_pagination', 'GitHub API pagination left api.github.com');
    result[relation] = parsed.toString();
  }
  return result;
}

async function requestJson(url, fetchImpl, wait) {
  if (new URL(url).origin !== apiRoot)
    throw new AuditFailure(
      'invalid_api_url',
      'Repository policy audit only permits api.github.com',
    );
  for (let attempt = 0; ; attempt++) {
    let response;
    try {
      response = await fetchImpl(url, {
        method: 'GET',
        headers: apiHeaders,
        redirect: 'error',
        signal: AbortSignal.timeout(15_000),
      });
    } catch (error) {
      if (attempt < retryDelays.length) {
        await wait(retryDelays[attempt]);
        continue;
      }
      throw new AuditFailure(
        'network_error',
        `Public GitHub API request failed (${error?.name ?? 'network error'})`,
      );
    }
    if (!response.ok) {
      if (retryableStatuses.has(response.status) && attempt < retryDelays.length) {
        await wait(retryDelays[attempt]);
        continue;
      }
      throw new AuditFailure('http_error', `Public GitHub API returned HTTP ${response.status}`);
    }
    let data;
    try {
      data = await response.json();
    } catch {
      throw new AuditFailure('invalid_json', 'Public GitHub API returned invalid JSON');
    }
    return { data, link: response.headers?.get('link') ?? null };
  }
}

async function collection(url, fetchImpl, wait) {
  const values = [],
    visited = new Set();
  let current = url;
  for (let page = 0; current; page++) {
    if (page >= 20 || visited.has(current))
      throw new AuditFailure('incomplete_pagination', 'GitHub API pagination is incomplete');
    visited.add(current);
    const { data, link } = await requestJson(current, fetchImpl, wait);
    if (!Array.isArray(data))
      throw new AuditFailure('invalid_collection', 'GitHub API returned an incomplete collection');
    values.push(...data);
    const links = pagination(link, current);
    const pageNumber = Number(new URL(current).searchParams.get('page') ?? 1);
    const lastPage = links.last ? Number(new URL(links.last).searchParams.get('page')) : null;
    const nextPageNumber = links.next ? Number(new URL(links.next).searchParams.get('page')) : null;
    if (
      (!links.next && lastPage && pageNumber < lastPage) ||
      (links.next &&
        (!Number.isSafeInteger(nextPageNumber) || nextPageNumber !== pageNumber + 1)) ||
      (links.next && lastPage && nextPageNumber > lastPage) ||
      (links.last && !Number.isSafeInteger(lastPage)) ||
      (!links.next && data.length >= 100 && !links.last) ||
      (!links.present && data.length >= 100)
    )
      throw new AuditFailure('incomplete_pagination', 'GitHub API pagination is incomplete');
    current = links.next;
  }
  return values;
}

function compareRuleset(policy, repository, ruleset, drifts) {
  const expected = policy.ruleset;
  const check = (path, expectedValue, actualValue) => {
    if (!equalValue(actualValue, expectedValue))
      drifts.push({ path, expected: expectedValue, actual: actualValue ?? null });
  };
  const checkSet = (path, expectedValue, actualValue) => {
    if (!equalStringSet(actualValue, expectedValue))
      drifts.push({ path, expected: expectedValue, actual: actualValue ?? null });
  };

  check('ruleset.id', repository.id, ruleset.id);
  check('ruleset.name', expected.name, ruleset.name);
  check('ruleset.source_type', expected.source_type, ruleset.source_type);
  check('ruleset.source', expected.source, ruleset.source);
  check('ruleset.target', expected.target, ruleset.target);
  check('ruleset.enforcement', expected.enforcement, ruleset.enforcement);
  checkSet(
    'ruleset.conditions.ref_name.include',
    expected.ref_name_include,
    ruleset.conditions?.ref_name?.include,
  );
  checkSet(
    'ruleset.conditions.ref_name.exclude',
    expected.ref_name_exclude,
    ruleset.conditions?.ref_name?.exclude,
  );
  checkSet(
    'ruleset.rule_types',
    expected.rule_types,
    (ruleset.rules ?? []).map((rule) => rule.type),
  );

  const pullRules = (ruleset.rules ?? []).filter((rule) => rule.type === 'pull_request');
  if (pullRules.length !== 1) {
    drifts.push({ path: 'ruleset.pull_request.count', expected: 1, actual: pullRules.length });
  } else {
    const parameters = pullRules[0].parameters ?? {};
    checkSet(
      'ruleset.pull_request.allowed_merge_methods',
      expected.pull_request.allowed_merge_methods,
      parameters.allowed_merge_methods,
    );
    check(
      'ruleset.pull_request.dismiss_stale_reviews_on_push',
      expected.pull_request.dismiss_stale_reviews_on_push,
      parameters.dismiss_stale_reviews_on_push,
    );
    check(
      'ruleset.pull_request.required_approving_review_count',
      expected.pull_request.required_approving_review_count,
      parameters.required_approving_review_count,
    );
    check(
      'ruleset.pull_request.required_review_thread_resolution',
      expected.pull_request.required_review_thread_resolution,
      parameters.required_review_thread_resolution,
    );
  }

  if (expected.empty_required_status_checks_rule) {
    const checksRules = (ruleset.rules ?? []).filter(
      (rule) => rule.type === 'required_status_checks',
    );
    const empty =
      checksRules.length === 1 &&
      Array.isArray(checksRules[0].parameters?.required_status_checks) &&
      checksRules[0].parameters.required_status_checks.length === 0;
    if (!empty)
      drifts.push({
        path: 'ruleset.required_status_checks',
        expected: 'one empty ruleset entry (classic branch protection is checked separately)',
        actual: checksRules.map((rule) => rule.parameters?.required_status_checks ?? null),
      });
  }

  return {
    name: expected.name,
    id: repository.id,
    target: ruleset.target,
    enforcement: ruleset.enforcement,
    rule_types: (ruleset.rules ?? []).map((rule) => rule.type).sort(),
  };
}

/**
 * Compare only public Workbench repository metadata and the named active ruleset.
 * Private repos, Projects and classic branch protection require a separate trusted reader.
 */
export async function auditRepositoryPolicy({
  policy = readJson(resolve(root, 'tools/config/repository-policy.json')),
  fetchImpl = globalThis.fetch,
  wait = (milliseconds) =>
    new Promise((resolveWait) => {
      setTimeout(resolveWait, milliseconds);
    }),
  checkedAt = new Date().toISOString(),
  sourceSha = process.env.GITHUB_SHA ?? 'unknown',
  executionRepository = process.env.GITHUB_REPOSITORY,
} = {}) {
  const base = {
    schema_version: 1,
    operation: 'ci.repository-policy',
    repository: policy?.repository ?? null,
    policy_schema_version: policy?.schema_version ?? null,
    checked_at: checkedAt,
    source_sha: sourceSha,
    coverage: ['public repository metadata', 'active default-branch ruleset'],
    not_publicly_verifiable: policy?.not_publicly_verifiable ?? [],
  };
  try {
    validatePolicy(policy);
    if (!/^[a-f0-9]{40}$/.test(sourceSha ?? ''))
      throw new AuditFailure('missing_source_sha', 'A complete policy source SHA is required');
    if (!Number.isFinite(Date.parse(checkedAt)))
      throw new AuditFailure('invalid_timestamp', 'A valid API check timestamp is required');
    if (executionRepository && executionRepository !== policy.repository)
      throw new AuditFailure(
        'wrong_repository',
        `This audit is restricted to ${policy.repository}`,
      );
    const [owner, name] = policy.repository.split('/');
    const repositoryPath = `${apiRoot}/repos/${owner}/${name}`;
    const { data: metadata } = await requestJson(repositoryPath, fetchImpl, wait);
    const drifts = [];
    const metadataCheck = (path, expected, actual) => {
      if (!equalValue(actual, expected)) drifts.push({ path, expected, actual: actual ?? null });
    };
    metadataCheck('repository.id', policy.repository_id, metadata.id);
    metadataCheck('repository.full_name', policy.repository, metadata.full_name);
    metadataCheck('repository.visibility', policy.visibility, metadata.visibility);
    metadataCheck('repository.default_branch', policy.default_branch, metadata.default_branch);

    const listed = await collection(
      `${repositoryPath}/rulesets?per_page=100&page=1`,
      fetchImpl,
      wait,
    );
    const matches = listed.filter((item) => item.name === policy.ruleset.name);
    if (matches.length !== 1) {
      drifts.push({
        path: 'ruleset.named_count',
        expected: 1,
        actual: matches.length,
      });
      return {
        ...base,
        status: drifts.length ? 'drift' : 'success',
        repository_metadata: {
          id: metadata.id,
          full_name: metadata.full_name,
          visibility: metadata.visibility,
          default_branch: metadata.default_branch,
        },
        ruleset: null,
        drift: drifts,
      };
    }
    const details = await requestJson(
      `${repositoryPath}/rulesets/${matches[0].id}`,
      fetchImpl,
      wait,
    );
    const observedRuleset = compareRuleset(policy, matches[0], details.data, drifts);
    return {
      ...base,
      status: drifts.length ? 'drift' : 'success',
      repository_metadata: {
        id: metadata.id,
        full_name: metadata.full_name,
        visibility: metadata.visibility,
        default_branch: metadata.default_branch,
      },
      ruleset: observedRuleset,
      drift: drifts,
    };
  } catch (error) {
    const code = error instanceof AuditFailure ? error.code : 'audit_error';
    return {
      ...base,
      status: 'blocked',
      error: {
        code,
        message:
          error instanceof AuditFailure
            ? error.message
            : 'Repository policy audit failed unexpectedly',
      },
    };
  }
}
