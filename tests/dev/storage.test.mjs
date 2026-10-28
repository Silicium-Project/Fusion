import test from 'node:test';
import assert from 'node:assert/strict';
import { generateKeyPairSync, verify } from 'node:crypto';
import {
  installationRecord,
  organizationArtifactLimit,
  remainingBudget,
  requireCoverage,
} from '../../tools/ci/storage-budget.mjs';
test('temporary storage has a hard ceiling and invalid usage fails closed', () => {
  assert.equal(remainingBudget(100, 50, 400), 250);
  for (const [a, b] of [
    [400, 1],
    [399, 1],
    [-1, 10],
    [NaN, 1],
    [1, Infinity],
  ])
    assert.throws(() => remainingBudget(a, b, 400));
});
test('the organization plan selects a conservative artifact cap and unknown plans fail closed', () => {
  const enterprise = organizationArtifactLimit({ plan: { name: 'enterprise' } });
  const free = organizationArtifactLimit({ plan: { name: 'free' } });
  const unknown = organizationArtifactLimit({});
  assert.equal(enterprise, 512 * 1024 ** 2);
  assert.equal(free, 400 * 1024 ** 2);
  assert.equal(unknown, free);
  assert.ok(remainingBudget(12 * 1024 ** 2, 392 * 1024 ** 2, enterprise) > 0);
  assert.throws(() => remainingBudget(12 * 1024 ** 2, 392 * 1024 ** 2, free));
});
test('an App restricted to selected repositories cannot measure the organization budget', () => {
  const installation = { repository_selection: 'all', account: { login: 'Silicium-Project' } };
  const repos = [{ id: 1, private: true, owner: { login: 'Silicium-Project' } }];
  const organization = { total_private_repos: 1, public_repos: 0 };
  assert.doesNotThrow(() => requireCoverage(installation, organization, repos));
  assert.throws(() =>
    requireCoverage({ ...installation, repository_selection: 'selected' }, organization, repos),
  );
  assert.throws(() =>
    requireCoverage(installation, { ...organization, total_private_repos: 2 }, repos),
  );
  assert.throws(() => requireCoverage(installation, organization, []));
  assert.throws(() =>
    requireCoverage({ ...installation, suspended_at: '2026-10-25' }, organization, repos),
  );
});

const { privateKey, publicKey } = generateKeyPairSync('rsa', { modulusLength: 2048 });
const identity = {
  id: '123',
  client: 'test-app-client',
  key: privateKey.export({ type: 'pkcs8', format: 'pem' }),
};

test('installation lookup uses a signed, bounded Bearer JWT and refuses redirects', async () => {
  const metadata = { repository_selection: 'all', account: { login: 'Silicium-Project' } };
  let calls = 0;
  const result = await installationRecord(identity, async (url, options) => {
    calls++;
    assert.equal(url, 'https://api.github.com/app/installations/123');
    assert.equal(options.redirect, 'error');
    assert.ok(options.signal instanceof AbortSignal);
    assert.match(options.headers.authorization, /^Bearer /);
    const [header, body, signature] = options.headers.authorization.slice(7).split('.');
    assert.deepEqual(JSON.parse(Buffer.from(header, 'base64url')), { alg: 'RS256', typ: 'JWT' });
    const claims = JSON.parse(Buffer.from(body, 'base64url'));
    const now = Math.floor(Date.now() / 1000);
    assert.equal(claims.iss, identity.client);
    assert.ok(claims.iat <= now && claims.iat >= now - 65);
    assert.ok(claims.exp > now && claims.exp <= now + 300);
    assert.ok(
      verify(
        'RSA-SHA256',
        Buffer.from(`${header}.${body}`),
        publicKey,
        Buffer.from(signature, 'base64url'),
      ),
    );
    return Response.json(metadata);
  });
  assert.equal(calls, 1);
  assert.deepEqual(result, metadata);
});

test('App metadata failures stop once and do not expose request or response secrets', async () => {
  for (const request of [
    async () => new Response('sensitive response body', { status: 401 }),
    async () => {
      throw new Error('sensitive request details');
    },
    async () => new Response('sensitive invalid JSON'),
  ]) {
    let calls = 0;
    await assert.rejects(
      installationRecord(identity, (...args) => {
        calls++;
        return request(...args);
      }),
      (error) => {
        assert.equal(error.exitCode, 3);
        assert.doesNotMatch(error.message, /sensitive|Bearer|PRIVATE KEY/);
        return true;
      },
    );
    assert.equal(calls, 1);
  }
});
