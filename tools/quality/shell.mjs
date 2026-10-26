/** ShellCheck is pinned by archive and executable hashes. No unverified tool cache. */
import { existsSync, readFileSync, writeFileSync, mkdirSync, chmodSync } from 'node:fs';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';
import { readJson, root, run, Failure } from '../lib/process.mjs';
import { trackedSources } from '../lib/workspace.mjs';
if (process.platform !== 'linux' || process.arch !== 'x64')
  throw new Failure('Shell qualification requires Linux x86-64', 2);
const pin = readJson(resolve(root, 'tools/config/shellcheck.json'));
const dir = resolve(root, '.artifacts/tools'),
  binary = resolve(dir, 'shellcheck');
const digest = (bytes) => createHash('sha256').update(bytes).digest('hex');
mkdirSync(dir, { recursive: true });
if (!existsSync(binary)) {
  const response = await fetch(pin.url, { signal: AbortSignal.timeout(30_000) });
  if (!response.ok) throw new Failure(`ShellCheck download failed: ${response.status}`, 4);
  const archive = Buffer.from(await response.arrayBuffer());
  if (digest(archive) !== pin.sha256) throw new Failure('ShellCheck archive checksum mismatch', 3);
  const file = resolve(dir, 'shellcheck.tar.xz');
  writeFileSync(file, archive);
  // Extract only the known member after the archive integrity check.
  run(['tar', '-xf', file, '-C', dir, '--strip-components=1', pin.member]);
  chmodSync(binary, 0o755);
}
if (digest(readFileSync(binary)) !== pin.binary_sha256)
  throw new Failure(
    'ShellCheck tool cache is corrupt; remove only .artifacts/tools/shellcheck and retry',
    3,
  );
const paths = trackedSources().filter(
  (path) =>
    (path.endsWith('.sh') || path === 'dev' || path.endsWith('/dev')) &&
    !path.startsWith('docs/archive/'),
);
for (const path of paths) run(['bash', '-n', path]);
const result = run(
  [binary, '--external-sources', '--source-path=SCRIPTDIR', '--severity=warning', ...paths],
  { allowFailure: true },
);
process.stdout.write(result.stdout);
process.stderr.write(result.stderr);
if (result.status) throw new Failure('Shell syntax or ShellCheck failed');
console.log(`ShellCheck ${pin.version}: ${paths.length} scripts`);
