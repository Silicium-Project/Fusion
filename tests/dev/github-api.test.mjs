import test from 'node:test';
import assert from 'node:assert/strict';
import { createClient } from '../../tools/lib/github.mjs';

test('REST reads retry transient HTTP/2 failures with bounded backoff', () => {
  const waits = [];
  let calls = 0;
  const client = createClient({
    execute: () => {
      calls++;
      return calls === 1
        ? { status: 1, stderr: 'stream error: stream ID 1; CANCEL; received from peer' }
        : { status: 0, stdout: '{"ok":true}', stderr: '' };
    },
    wait: (milliseconds) => waits.push(milliseconds),
  });

  assert.deepEqual(client.api('repos/Silicium-Project/Workbench'), { ok: true });
  assert.equal(calls, 2);
  assert.deepEqual(waits, [250]);
});

test('REST reads stop after three attempts and preserve a clear failure', () => {
  const waits = [];
  let calls = 0;
  const client = createClient({
    execute: () => {
      calls++;
      return { status: 1, stderr: 'HTTP 503 Service Unavailable' };
    },
    wait: (milliseconds) => waits.push(milliseconds),
  });

  assert.throws(
    () => client.api('repos/Silicium-Project/Workbench'),
    (error) => error.exitCode === 3 && /503/.test(error.message),
  );
  assert.equal(calls, 3);
  assert.deepEqual(waits, [250, 750]);
});

test('GraphQL queries retry, but GraphQL mutations never replay', () => {
  let queryCalls = 0;
  const queryClient = createClient({
    execute: () =>
      ++queryCalls === 1
        ? { status: 1, stderr: 'connection reset by peer' }
        : { status: 0, stdout: '{"data":{"viewer":{"login":"luis"}}}', stderr: '' },
    wait: () => {},
  });
  assert.deepEqual(queryClient.graphql('# read only\nquery { viewer { login } }'), {
    viewer: { login: 'luis' },
  });
  assert.equal(queryCalls, 2);

  let mutationCalls = 0;
  const mutationClient = createClient({
    execute: () => {
      mutationCalls++;
      return { status: 1, stderr: 'HTTP 502 Bad Gateway' };
    },
    wait: () => assert.fail('mutations must not wait or retry'),
  });
  assert.throws(() =>
    mutationClient.graphql('mutation { updateProjectV2ItemFieldValue { projectV2Item { id } } }'),
  );
  assert.equal(mutationCalls, 1);
});

test('REST writes and rate-limit refusals are never retried', () => {
  let writes = 0;
  const client = createClient({
    execute: () => {
      writes++;
      return { status: 1, stderr: 'HTTP 503 Service Unavailable' };
    },
    wait: () => assert.fail('writes must not wait or retry'),
  });
  assert.throws(() =>
    client.api('repos/Silicium-Project/Workbench/issues', { method: 'POST', body: {} }),
  );
  assert.equal(writes, 1);

  const limited = createClient({
    execute: () => ({ status: 1, stderr: 'HTTP 429 Too Many Requests' }),
    wait: () => assert.fail('rate limits should be surfaced for a later run'),
  });
  assert.throws(
    () => limited.api('repos/Silicium-Project/Workbench'),
    (error) => error.exitCode === 4 && /429/.test(error.message),
  );
});

test('repository-scoped tokens are passed only through the request environment', () => {
  let request;
  const client = createClient({
    execute: (args, options) => {
      request = { args, options };
      return { status: 0, stdout: '{"ok":true}', stderr: '' };
    },
  });

  client.api('repos/Silicium-Project/Integration/pulls?state=all', {
    token: 'ephemeral-integration-token',
  });
  assert.deepEqual(request.options.env, { GH_TOKEN: 'ephemeral-integration-token' });
  assert.ok(request.args.every((argument) => !argument.includes('ephemeral-integration-token')));
});
