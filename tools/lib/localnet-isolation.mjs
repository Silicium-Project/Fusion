/** Agave 2.3 binds RPC/faucet broadly: isolate both the network and validator process tree. */
import { Failure } from './process.mjs';
export function assertIsolatedLocalnet(parentNamespace, currentNamespace, interfaces) {
  if (!parentNamespace || parentNamespace === currentNamespace)
    throw new Failure('Localnet must run in a distinct network namespace', 3);
  const addresses = Object.values(interfaces).flat();
  if (!addresses.length || addresses.some((address) => !address.internal))
    throw new Failure('Localnet namespace must expose loopback only', 3);
}
export function localnetCommand({ userNamespaces, githubActions, uid, gid, node, script, config }) {
  const isolation = ['--net', '--pid', '--fork', '--mount-proc', '--kill-child=KILL'];
  if (userNamespaces)
    return [
      'unshare',
      '--user',
      '--map-root-user',
      ...isolation,
      'sh',
      '-ceu',
      'ip link set lo up\nexec "$@"',
      'silicium-localnet',
      node,
      script,
      config,
    ];
  if (githubActions && Number.isInteger(uid) && Number.isInteger(gid))
    return [
      'sudo',
      '-n',
      'unshare',
      ...isolation,
      'sh',
      '-ceu',
      'ip link set lo up\nexec setpriv --reuid "$1" --regid "$2" --clear-groups --no-new-privs --reset-env "$3" "$4" "$5"',
      'silicium-localnet',
      String(uid),
      String(gid),
      node,
      script,
      config,
    ];
  throw new Failure(
    'Localnet requires unprivileged network/PID namespaces on Linux; use the documented GitHub runner when unavailable. No host-network fallback is allowed.',
    2,
  );
}
