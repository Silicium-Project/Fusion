/** Run the separately installed, read-only host diagnostic entry point. */
import { resolve } from 'node:path';
import { root, run, writeJson, Failure } from '../lib/process.mjs';
import { deploymentSsh } from '../lib/ssh.mjs';
const channel = process.env.RELEASE_CHANNEL;
if (!['dev', 'prod'].includes(channel))
  throw new Failure('Explicit diagnostic channel required', 2);
const ssh = deploymentSsh();
try {
  const result = run(
    [
      'ssh',
      ...ssh.args,
      ssh.destination,
      `sudo -n /usr/local/sbin/silicium-diagnose --channel ${channel}`,
    ],
    { timeout: 90_000 },
  );
  const report = JSON.parse(result.stdout);
  if (report.schema_version !== 1 || report.channel !== channel)
    throw new Failure('Unexpected host diagnostic report');
  writeJson(resolve(root, '.artifacts/diagnostics/host.json'), report);
  console.log(
    JSON.stringify({
      schema_version: 1,
      channel,
      status: 'observed',
      cpu_busy_percent: report.cpu_busy_percent,
      health: report.health,
      rpc: report.rpc,
    }),
  );
} finally {
  ssh.close();
}
