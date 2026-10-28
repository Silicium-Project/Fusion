import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';
import {
  verifyPublicWorkbenchQualification,
  writePublicQualificationOutputs,
} from '../../tools/lib/public-ci-evidence.mjs';
import { readJson, root } from '../../tools/lib/process.mjs';

const require = createRequire(resolve(root, 'tools/quality/package.json'));
const Ajv = require('ajv');
const validateEvidence = new Ajv({ allErrors: true }).compile(
  readJson(resolve(root, 'contracts/ci/public-workbench-qualification-v1.schema.json')),
);

const sha = 'a'.repeat(40);
const timestamp = 'Tue, 27 Oct 2026 11:00:00 GMT';

function apiResponse(checks, { status = 200, date = timestamp, link = null } = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: {
      get: (name) => {
        const key = name.toLowerCase();
        return key === 'date' ? date : key === 'link' ? link : null;
      },
    },
    json: async () => checks,
  };
}

function check(overrides = {}) {
  return {
    id: 123,
    name: 'ci/required',
    status: 'completed',
    conclusion: 'success',
    head_sha: sha,
    app: { slug: 'github-actions' },
    ...overrides,
  };
}

test('accepts only the exact successful required check on current Workbench main', async () => {
  const calls = [];
  const result = await verifyPublicWorkbenchQualification({
    workbenchSha: sha,
    fetchImpl: async (url, options) => {
      calls.push({ url: String(url), options });
      return apiResponse({ total_count: 1, check_runs: [check()] });
    },
  });
  assert.equal(result.status, 'success');
  assert.equal(result.source_sha, sha);
  assert.equal(result.check_run_id, 123);
  assert.equal(result.api_timestamp, '2026-10-27T11:00:00.000Z');
  assert.equal(validateEvidence(result), true, JSON.stringify(validateEvidence.errors));
  assert.equal(calls.length, 1);
  assert.match(calls[0].url, /commits\/main\/check-runs\?filter=latest/);
  assert.equal(calls[0].options.redirect, 'error');
  assert.equal(Object.hasOwn(calls[0].options.headers, 'authorization'), false);
});

test('fails closed for stale, missing, duplicated, pending or unsuccessful required checks', async (t) => {
  for (const [name, payload, code] of [
    [
      'stale SHA',
      { total_count: 1, check_runs: [check({ head_sha: 'b'.repeat(40) })] },
      'public_ci_stale',
    ],
    [
      'missing check',
      { total_count: 1, check_runs: [{ ...check(), name: 'other' }] },
      'public_ci_missing',
    ],
    [
      'duplicate check',
      { total_count: 2, check_runs: [check(), check({ id: 124 })] },
      'public_ci_ambiguous',
    ],
    [
      'pending check',
      { total_count: 1, check_runs: [check({ status: 'in_progress', conclusion: null })] },
      'public_ci_failed',
    ],
    [
      'failed check',
      { total_count: 1, check_runs: [check({ conclusion: 'failure' })] },
      'public_ci_failed',
    ],
    [
      'unexpected check app',
      { total_count: 1, check_runs: [check({ app: { slug: 'other-app' } })] },
      'public_ci_failed',
    ],
    [
      'incomplete page',
      { total_count: 101, check_runs: [check()] },
      'public_ci_pagination_incomplete',
    ],
  ]) {
    await t.test(name, async () => {
      const result = await verifyPublicWorkbenchQualification({
        workbenchSha: sha,
        fetchImpl: async () => apiResponse(payload),
      });
      assert.equal(result.status, 'blocked');
      assert.equal(result.error.code, code);
      assert.equal(validateEvidence(result), true, JSON.stringify(validateEvidence.errors));
    });
  }
});

test('blocks API errors, pagination, missing timestamps, invalid JSON and transport failures without exposing them', async (t) => {
  for (const [name, fetchImpl, code] of [
    ['HTTP rate limit', async () => apiResponse({}, { status: 429 }), 'public_ci_http_error'],
    [
      'missing timestamp',
      async () => apiResponse({ total_count: 1, check_runs: [check()] }, { date: null }),
      'public_ci_timestamp_missing',
    ],
    [
      'next page',
      async () =>
        apiResponse(
          { total_count: 1, check_runs: [check()] },
          { link: '<https://api.github.com/?page=2>; rel="next"' },
        ),
      'public_ci_pagination_incomplete',
    ],
    [
      'invalid JSON',
      async () => ({
        ...apiResponse({}),
        json: async () => {
          throw new Error('PRIVATE_CANARY');
        },
      }),
      'public_ci_invalid_json',
    ],
    [
      'timeout',
      async () => {
        const error = new Error('PRIVATE_CANARY');
        error.name = 'TimeoutError';
        throw error;
      },
      'public_ci_timeout',
    ],
    [
      'network failure',
      async () => {
        throw new Error('PRIVATE_CANARY');
      },
      'public_ci_unavailable',
    ],
  ]) {
    await t.test(name, async () => {
      const result = await verifyPublicWorkbenchQualification({ workbenchSha: sha, fetchImpl });
      assert.equal(result.status, 'blocked');
      assert.equal(result.error.code, code);
      assert.doesNotMatch(JSON.stringify(result), /PRIVATE_CANARY/);
    });
  }
});

test('writes bounded, newline-safe GitHub step outputs', (t) => {
  const directory = mkdtempSync(resolve(tmpdir(), 'silicium-public-ci-'));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  const output = resolve(directory, 'github-output');
  writePublicQualificationOutputs(
    {
      status: 'blocked',
      source_sha: sha,
      check_name: 'ci/required',
      check_run_id: null,
      check_status: null,
      conclusion: null,
      app_slug: null,
      api_timestamp: null,
      error: { code: 'public_ci_failed', message: 'line one\nline two' },
    },
    output,
  );
  const contents = readFileSync(output, 'utf8');
  assert.match(contents, /status=blocked/);
  assert.match(contents, /error_message=line one line two/);
  assert.doesNotMatch(contents, /\nline two/);
});
