import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runLive } from '../../tools/lib/process.mjs';
const node = process.execPath;
test('runLive reports success, failure and a timeout without throwing', () => {
  const ok = runLive([node, '-e', 'process.exit(0)']);
  assert.equal(ok.status, 0);
  assert.equal(ok.timedOut, false);
  const failed = runLive([node, '-e', 'process.exit(3)']);
  assert.equal(failed.status, 3);
  assert.equal(failed.timedOut, false);
  const hung = runLive([node, '-e', 'setInterval(() => {}, 1000)'], { timeout: 300 });
  assert.equal(hung.timedOut, true);
  assert.notEqual(hung.status, 0);
});
test('the Solana task phases end before the 45 minute job limit', () => {
  const task = readFileSync(new URL('../../tools/tasks/solana.mjs', import.meta.url), 'utf8');
  const inner = readFileSync(
    new URL('../../tools/tasks/solana-localnet.mjs', import.meta.url),
    'utf8',
  );
  const minutes = (source, name) =>
    Number(source.match(new RegExp(`${name} = (\\d+) \\* 60_000`))[1]);
  const build = minutes(task, 'buildTimeoutMs');
  const localnet = minutes(task, 'localnetTimeoutMs');
  const test = minutes(inner, 'testTimeoutMs');
  assert.ok(test < localnet, 'anchor test must end before the localnet phase');
  assert.ok(build + localnet < 45, 'build and localnet must end before the job timeout');
  assert.doesNotMatch(task, /2_400_000/);
  assert.doesNotMatch(inner, /2_400_000/);
});
