import test from 'node:test';
import assert from 'node:assert/strict';
import { assertIsolatedLocalnet, localnetCommand } from '../../tools/lib/localnet-isolation.mjs';
test('a shared host namespace or external interface blocks localnet', () => {
  const loopback = { lo: [{ address: '127.0.0.1', internal: true }] };
  assert.doesNotThrow(() => assertIsolatedLocalnet('net:[1]', 'net:[2]', loopback));
  assert.throws(() => assertIsolatedLocalnet('net:[1]', 'net:[1]', loopback));
  assert.throws(() =>
    assertIsolatedLocalnet('net:[1]', 'net:[2]', {
      ...loopback,
      eth0: [{ address: '10.0.0.2', internal: false }],
    }),
  );
  assert.throws(() => assertIsolatedLocalnet('net:[1]', 'net:[2]', {}));
});
test('local unprivileged isolation passes paths as data and kills the whole namespace on exit', () => {
  const args = {
    userNamespaces: true,
    node: '/node with spaces',
    script: '/task.mjs',
    config: '/config.json',
  };
  const command = localnetCommand(args);
  for (const flag of ['--user', '--net', '--pid', '--kill-child=KILL'])
    assert.ok(command.includes(flag));
  assert.deepEqual(command.slice(-3), [args.node, args.script, args.config]);
  assert.equal(command[0], 'unshare');
});
test('only ephemeral GitHub runners can use the privileged namespace bootstrap and drop privilege', () => {
  const args = {
    userNamespaces: false,
    uid: 1001,
    gid: 1001,
    node: '/node',
    script: '/task',
    config: '/config',
  };
  assert.throws(() => localnetCommand(args), /No host-network fallback/);
  const command = localnetCommand({ ...args, githubActions: true });
  assert.equal(command[0], 'sudo');
  assert.ok(command.includes('-n'));
  assert.ok(command.some((arg) => arg.includes('--clear-groups --no-new-privs --reset-env')));
});
