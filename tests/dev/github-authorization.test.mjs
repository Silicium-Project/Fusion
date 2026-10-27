import test from 'node:test';
import assert from 'node:assert/strict';
import {
  authorizeInternalPullRequest,
  githubGetJson,
} from '../../tools/lib/github-authorization.mjs';

const quietSleep = async () => {};

function response(status, body = {}) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

test('GitHub API GET retries bounded transient server responses with backoff', async (t) => {
  for (const status of [500, 502, 503, 504]) {
    await t.test(`HTTP ${status}`, async () => {
      const calls = [];
      const delays = [];
      const result = await githubGetJson('repos/Silicium-Project/Workbench/pulls/1', {
        token: 'fixture-token',
        sleepImpl: async (milliseconds) => delays.push(milliseconds),
        fetchImpl: async (url, options) => {
          calls.push({ url: String(url), authorization: options.headers.authorization });
          return calls.length < 3 ? response(status) : response(200, { number: 1 });
        },
      });

      assert.deepEqual(result, { number: 1 });
      assert.equal(calls.length, 3);
      assert.deepEqual(delays, [250, 1000]);
      assert.ok(calls.every(({ url }) => url.startsWith('https://api.github.com/')));
      assert.ok(calls.every(({ authorization }) => authorization === 'Bearer fixture-token'));
    });
  }
});

test('network and timeout failures retry, with a hard three-attempt limit', async () => {
  const delays = [];
  let calls = 0;
  const value = await githubGetJson('repos/Silicium-Project/Workbench/pulls/1', {
    token: 'fixture-token',
    sleepImpl: async (milliseconds) => delays.push(milliseconds),
    fetchImpl: async () => {
      calls += 1;
      if (calls === 1)
        throw Object.assign(new Error('temporary timeout'), { name: 'TimeoutError' });
      if (calls === 2) throw new TypeError('temporary connection failure');
      return response(200, { number: 1 });
    },
  });
  assert.deepEqual(value, { number: 1 });
  assert.equal(calls, 3);
  assert.deepEqual(delays, [250, 1000]);

  calls = 0;
  delays.length = 0;
  await assert.rejects(
    githubGetJson('repos/Silicium-Project/Workbench/pulls/1', {
      token: 'fixture-token',
      sleepImpl: async (milliseconds) => delays.push(milliseconds),
      fetchImpl: async () => {
        calls += 1;
        return response(502);
      },
    }),
    /HTTP 502/,
  );
  assert.equal(calls, 3);
  assert.deepEqual(delays, [250, 1000]);
});

test('authorization metadata failures outside transient server errors are not retried', async (t) => {
  for (const status of [401, 403, 404, 429]) {
    await t.test(`HTTP ${status}`, async () => {
      let calls = 0;
      await assert.rejects(
        githubGetJson('repos/Silicium-Project/Workbench/pulls/1', {
          token: 'fixture-token',
          sleepImpl: quietSleep,
          fetchImpl: async () => {
            calls += 1;
            return response(status);
          },
        }),
        new RegExp(`HTTP ${status}`),
      );
      assert.equal(calls, 1);
    });
  }

  let calls = 0;
  await assert.rejects(
    githubGetJson('repos/Silicium-Project/Workbench/pulls/1', {
      token: 'fixture-token',
      sleepImpl: quietSleep,
      fetchImpl: async () => {
        calls += 1;
        return {
          ok: true,
          json: async () => {
            throw new SyntaxError('bad JSON');
          },
        };
      },
    }),
    /invalid JSON/,
  );
  assert.equal(calls, 1);
});

test('authorization accepts only same-repository pull requests by team writers', async () => {
  const calls = [];
  const result = await authorizeInternalPullRequest({
    repository: 'Silicium-Project/Workbench',
    number: '42',
    token: 'fixture-token',
    sleepImpl: quietSleep,
    fetchImpl: async (url) => {
      calls.push(String(url));
      if (String(url).includes('/pulls/'))
        return response(200, {
          head: { repo: { id: 10 } },
          base: { repo: { id: 10 } },
          user: { login: 'trusted-user' },
        });
      return response(200, { permission: 'write' });
    },
  });

  assert.deepEqual(result, {
    pull_request: 42,
    same_repository: true,
    permission: 'write',
  });
  assert.equal(calls.length, 2);
  assert.ok(calls[1].endsWith('/collaborators/trusted-user/permission'));
});

test('forks, missing source repositories, and insufficient permissions are rejected', async (t) => {
  for (const pullRequest of [
    { head: { repo: { id: 11 } }, base: { repo: { id: 10 } }, user: { login: 'external' } },
    { head: { repo: null }, base: { repo: { id: 10 } }, user: { login: 'external' } },
  ]) {
    await t.test('untrusted source', async () => {
      let calls = 0;
      await assert.rejects(
        authorizeInternalPullRequest({
          repository: 'Silicium-Project/Workbench',
          number: 42,
          token: 'fixture-token',
          sleepImpl: quietSleep,
          fetchImpl: async () => {
            calls += 1;
            return response(200, pullRequest);
          },
        }),
        /External contributions remain disabled/,
      );
      assert.equal(calls, 1);
    });
  }

  await assert.rejects(
    authorizeInternalPullRequest({
      repository: 'Silicium-Project/Workbench',
      number: 42,
      token: 'fixture-token',
      sleepImpl: quietSleep,
      fetchImpl: async (url) =>
        String(url).includes('/pulls/')
          ? response(200, {
              head: { repo: { id: 10 } },
              base: { repo: { id: 10 } },
              user: { login: 'read-only-user' },
            })
          : response(200, { permission: 'read' }),
    }),
    /Team write permission/,
  );
});

test('invalid repository and pull request input are rejected before the API call', async () => {
  let calls = 0;
  const options = {
    token: 'fixture-token',
    sleepImpl: quietSleep,
    fetchImpl: async () => {
      calls += 1;
      return response(200);
    },
  };
  await assert.rejects(
    authorizeInternalPullRequest({ repository: 'invalid-repository', number: 1, ...options }),
    /owner\/repository/,
  );
  await assert.rejects(
    authorizeInternalPullRequest({
      repository: 'Silicium-Project/Workbench',
      number: '0',
      ...options,
    }),
    /pull request number/,
  );
  await assert.rejects(
    githubGetJson('https://attacker.example/path', options),
    /stay on api.github.com/,
  );
  assert.equal(calls, 0);
});
