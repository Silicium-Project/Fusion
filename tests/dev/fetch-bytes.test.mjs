import test from 'node:test';
import assert from 'node:assert/strict';
import { fetchBytes } from '../../tools/lib/fetch-bytes.mjs';
const body = (text, status = 200) => new Response(text, { status });
const noSleep = async () => {};
test('a dropped connection is retried and the third attempt succeeds', async () => {
  let calls = 0;
  const delays = [];
  const bytes = await fetchBytes('https://example.test/tool', {
    request: async () => {
      calls++;
      if (calls < 3)
        throw Object.assign(new TypeError('fetch failed'), { cause: { code: 'UND_ERR_SOCKET' } });
      return body('ok');
    },
    sleep: async (ms) => delays.push(ms),
  });
  assert.equal(bytes.toString(), 'ok');
  assert.equal(calls, 3);
  assert.deepEqual(delays, [2000, 8000]);
});
test('server errors and rate limits are retried, other client errors are not', async () => {
  for (const status of [408, 429, 500, 503]) {
    let calls = 0;
    const bytes = await fetchBytes('https://example.test/tool', {
      request: async () => (++calls === 1 ? body('', status) : body('ok')),
      sleep: noSleep,
    });
    assert.equal(bytes.toString(), 'ok', String(status));
  }
  for (const status of [400, 403, 404]) {
    let calls = 0;
    await assert.rejects(
      fetchBytes('https://example.test/tool', {
        request: async () => (++calls, body('', status)),
        sleep: noSleep,
      }),
      { message: `Download failed: HTTP ${status}`, exitCode: 4 },
    );
    assert.equal(calls, 1);
  }
});
test('the attempts are bounded and the last failure is reported', async () => {
  let calls = 0;
  await assert.rejects(
    fetchBytes('https://example.test/tool', {
      request: async () => {
        calls++;
        throw Object.assign(new TypeError('fetch failed'), { cause: { code: 'UND_ERR_SOCKET' } });
      },
      sleep: noSleep,
    }),
    { message: 'Download failed: UND_ERR_SOCKET', exitCode: 4 },
  );
  assert.equal(calls, 3);
  calls = 0;
  await assert.rejects(
    fetchBytes('https://example.test/tool', {
      attempts: 2,
      request: async () => (++calls, body('', 502)),
      sleep: noSleep,
    }),
    { message: 'Download failed: HTTP 502' },
  );
  assert.equal(calls, 2);
});
