import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { readJson } from '../../tools/lib/process.mjs';
import { auditRepositoryPolicy } from '../../tools/lib/repository-policy.mjs';
import { root } from '../../tools/lib/process.mjs';
import { workspaceConfig, workspaceLock } from '../../tools/lib/workspace.mjs';

const policy = readJson(new URL('../../tools/config/repository-policy.json', import.meta.url));
const workspace = workspaceConfig();
const lock = workspaceLock();
const require = createRequire(resolve(root, 'tools/quality/package.json'));
const Ajv = require('ajv');
const validateReport = new Ajv({ allErrors: true }).compile(
  readJson(new URL('../../contracts/ci/repository-policy-report-v1.schema.json', import.meta.url)),
);
const repositoryUrl = 'https://api.github.com/repos/Silicium-Project/Workbench';
const rulesetsUrl = `${repositoryUrl}/rulesets?per_page=100&page=1`;
const rulesetUrl = `${repositoryUrl}/rulesets/23931183`;
const apiDate = 'Tue, 27 Oct 2026 12:00:00 GMT';
const fixed = {
  checkedAt: '2026-10-27T12:00:00.000Z',
  sourceSha: 'a'.repeat(40),
  executionRepository: 'Silicium-Project/Workbench',
};

function response(data, { status = 200, link = null, date = apiDate } = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: {
      get: (name) =>
        name.toLowerCase() === 'link' ? link : name.toLowerCase() === 'date' ? date : null,
    },
    json: async () => data,
  };
}

function liveResponses() {
  return new Map([
    [
      repositoryUrl,
      {
        id: 1304063299,
        full_name: 'Silicium-Project/Workbench',
        visibility: 'public',
        default_branch: 'main',
      },
    ],
    [rulesetsUrl, [{ id: 23931183, name: 'Protect Main' }]],
    [
      rulesetUrl,
      {
        id: 23931183,
        name: 'Protect Main',
        source_type: 'Repository',
        source: 'Silicium-Project/Workbench',
        target: 'branch',
        enforcement: 'active',
        conditions: { ref_name: { include: ['~DEFAULT_BRANCH'], exclude: [] } },
        rules: [
          { type: 'non_fast_forward' },
          {
            type: 'pull_request',
            parameters: {
              allowed_merge_methods: ['merge'],
              dismiss_stale_reviews_on_push: true,
              required_approving_review_count: 0,
              required_review_thread_resolution: true,
            },
          },
          {
            type: 'required_status_checks',
            parameters: { required_status_checks: [] },
          },
        ],
      },
    ],
  ]);
}

function mockFetch(responses, requests = []) {
  return async (url, options) => {
    requests.push({ url: String(url), headers: options.headers, redirect: options.redirect });
    const item = responses.get(String(url));
    if (!item) throw new Error(`Unexpected request: ${url}`);
    return item.data === undefined ? response(item) : response(item.data, item.options);
  };
}

test('public ruleset audit proves the checked Workbench SHA and timestamp without credentials', async () => {
  const requests = [];
  const report = await auditRepositoryPolicy({
    ...fixed,
    policy,
    fetchImpl: mockFetch(liveResponses(), requests),
  });
  assert.equal(report.status, 'success');
  assert.equal(validateReport(report), true, validateReport.errors);
  assert.equal(report.repository_metadata.default_branch, 'main');
  assert.equal(report.ruleset.id, 23931183);
  assert.equal(report.checked_at, fixed.checkedAt);
  assert.equal(report.source_sha, fixed.sourceSha);
  assert.equal(report.registry.workbench.default_branch, 'main');
  assert.equal(report.registry.integration.repository, 'Silicium-Project/Integration');
  assert.equal(report.registry.components.api.commit, lock.components.api.commit);
  assert.ok(report.not_publicly_verifiable.includes('ruleset bypass actors'));
  assert.deepEqual(
    report.api_observations.map((observation) => observation.resource),
    ['repository.metadata', 'repository.rulesets', 'repository.ruleset'],
  );
  assert.ok(report.api_observations.every((observation) => observation.api_timestamp));
  assert.ok(
    report.api_observations.every((observation) => observation.api_timestamp.endsWith('Z')),
  );
  assert.equal(requests.length, 3);
  assert.ok(
    requests.every(
      ({ headers, redirect }) => !Object.hasOwn(headers, 'authorization') && redirect === 'error',
    ),
  );
});

test('visibility, branch, enforcement and merge-method drift are reported together', async () => {
  const responses = liveResponses();
  responses.set(repositoryUrl, {
    id: 1304063299,
    full_name: 'Silicium-Project/Workbench',
    visibility: 'private',
    default_branch: 'integration',
  });
  responses.set(rulesetUrl, {
    ...responses.get(rulesetUrl),
    enforcement: 'disabled',
    rules: responses.get(rulesetUrl).rules.map((rule) =>
      rule.type === 'pull_request'
        ? {
            ...rule,
            parameters: { ...rule.parameters, allowed_merge_methods: ['merge', 'squash'] },
          }
        : rule,
    ),
  });
  const report = await auditRepositoryPolicy({
    ...fixed,
    policy,
    fetchImpl: mockFetch(responses),
  });
  assert.equal(report.status, 'drift');
  assert.equal(validateReport(report), true, validateReport.errors);
  const paths = report.drift.map((item) => item.path);
  assert.ok(paths.includes('repository.visibility'));
  assert.ok(paths.includes('repository.default_branch'));
  assert.ok(paths.includes('ruleset.enforcement'));
  assert.ok(paths.includes('ruleset.pull_request.allowed_merge_methods'));
});

test('ruleset list pagination is followed and duplicate named rulesets fail visibly', async () => {
  const responses = liveResponses();
  responses.set(rulesetsUrl, {
    data: [{ id: 1, name: 'Other' }],
    options: {
      link: '<https://api.github.com/repos/Silicium-Project/Workbench/rulesets?per_page=100&page=2>; rel="next"',
    },
  });
  const next =
    'https://api.github.com/repos/Silicium-Project/Workbench/rulesets?per_page=100&page=2';
  responses.set(next, [
    { id: 23931183, name: 'Protect Main' },
    { id: 23931184, name: 'Protect Main' },
  ]);
  const requests = [];
  const report = await auditRepositoryPolicy({
    ...fixed,
    policy,
    fetchImpl: mockFetch(responses, requests),
  });
  assert.equal(report.status, 'drift');
  assert.deepEqual(report.drift, [{ path: 'ruleset.named_count', expected: 1, actual: 2 }]);
  assert.deepEqual(
    report.api_observations
      .filter((observation) => observation.resource === 'repository.rulesets')
      .map((observation) => observation.page),
    [1, 2],
  );
  assert.ok(requests.some((request) => request.url === next));
});

test('an API response without its server timestamp blocks the audit and preserves prior evidence', async () => {
  const responses = liveResponses();
  responses.set(rulesetsUrl, { data: [], options: { date: null } });
  const report = await auditRepositoryPolicy({
    ...fixed,
    policy,
    fetchImpl: mockFetch(responses),
  });
  assert.equal(report.status, 'blocked');
  assert.equal(validateReport(report), true, validateReport.errors);
  assert.equal(report.error.code, 'missing_api_timestamp');
  assert.deepEqual(
    report.api_observations.map((item) => item.resource),
    ['repository.metadata'],
  );
  assert.equal(report.repository_metadata.full_name, 'Silicium-Project/Workbench');
});

test('API authorization or rate-limit failure blocks the report without exposing response text', async () => {
  const fetchImpl = async () => response({ message: 'SECRET_CANARY' }, { status: 403 });
  const report = await auditRepositoryPolicy({ ...fixed, policy, fetchImpl });
  assert.equal(report.status, 'blocked');
  assert.equal(report.error.code, 'http_error');
  assert.match(report.error.message, /HTTP 403/);
  assert.doesNotMatch(JSON.stringify(report), /SECRET_CANARY/);
});

test('transient public API rate limits retry a bounded number of times', async () => {
  const responses = liveResponses();
  let first = true;
  const waits = [];
  const fetchImpl = async (url, options) => {
    if (url === repositoryUrl && first) {
      first = false;
      return response({}, { status: 429 });
    }
    return mockFetch(responses)(url, options);
  };
  const report = await auditRepositoryPolicy({
    ...fixed,
    policy,
    fetchImpl,
    wait: async (milliseconds) => waits.push(milliseconds),
  });
  assert.equal(report.status, 'success');
  assert.deepEqual(waits, [250]);
});

test('API pagination cannot redirect the read-only audit outside api.github.com', async () => {
  const responses = liveResponses();
  responses.set(rulesetsUrl, {
    data: [],
    options: { link: '<https://example.com/steal>; rel="next"' },
  });
  const report = await auditRepositoryPolicy({
    ...fixed,
    policy,
    fetchImpl: mockFetch(responses),
  });
  assert.equal(report.status, 'blocked');
  assert.equal(report.error.code, 'invalid_pagination');
});

test('an API collection that signals more pages but omits the next link is blocked', async () => {
  const responses = liveResponses();
  responses.set(rulesetsUrl, {
    data: Array.from({ length: 100 }, (_, index) => ({ id: index + 1, name: 'Other' })),
    options: {
      link: '<https://api.github.com/repos/Silicium-Project/Workbench/rulesets?per_page=100&page=3>; rel="last"',
    },
  });
  const report = await auditRepositoryPolicy({
    ...fixed,
    policy,
    fetchImpl: mockFetch(responses),
  });
  assert.equal(report.status, 'blocked');
  assert.equal(report.error.code, 'incomplete_pagination');
});

test('wrong repository, unsupported manifest and incomplete provenance fail closed', async () => {
  let requests = 0;
  const fetchImpl = async () => {
    requests++;
    return response({});
  };
  const wrongRepository = await auditRepositoryPolicy({
    ...fixed,
    policy,
    executionRepository: 'attacker/Workbench',
    fetchImpl,
  });
  assert.equal(wrongRepository.status, 'blocked');
  assert.equal(wrongRepository.error.code, 'wrong_repository');
  assert.equal(requests, 0);

  const unsupported = await auditRepositoryPolicy({
    ...fixed,
    policy: { ...policy, schema_version: 2 },
    fetchImpl,
  });
  assert.equal(unsupported.status, 'blocked');
  assert.equal(unsupported.error.code, 'invalid_policy');

  const missingSha = await auditRepositoryPolicy({
    ...fixed,
    sourceSha: 'unknown',
    policy,
    fetchImpl,
  });
  assert.equal(missingSha.status, 'blocked');
  assert.equal(missingSha.error.code, 'missing_source_sha');
  assert.equal(requests, 0);
});

test('public API audit is bound to the versioned registry and exact local pins', async () => {
  let requests = 0;
  const fetchImpl = async () => {
    requests++;
    return response({});
  };
  const invalidOwner = await auditRepositoryPolicy({
    ...fixed,
    policy,
    workspace: { ...workspace, owner: 'Unrelated-Organization' },
    lock,
    fetchImpl,
  });
  assert.equal(invalidOwner.status, 'blocked');
  assert.equal(invalidOwner.error.code, 'invalid_registry');

  const mismatchedPolicy = await auditRepositoryPolicy({
    ...fixed,
    policy: { ...policy, repository: 'Silicium-Project/Other' },
    workspace,
    lock,
    fetchImpl,
  });
  assert.equal(mismatchedPolicy.status, 'blocked');
  assert.equal(mismatchedPolicy.error.code, 'invalid_policy');

  const localDrift = await auditRepositoryPolicy({
    ...fixed,
    policy,
    workspace,
    lock,
    inspectWorkspace: () => ({ status: 'blocked' }),
    fetchImpl,
  });
  assert.equal(localDrift.status, 'blocked');
  assert.equal(localDrift.error.code, 'workspace_drift');
  assert.equal(requests, 0);
});
