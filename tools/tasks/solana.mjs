/** Build SBF once, then qualify that exact binary in a disposable isolated localnet. */
import { run, runLive, root, readJson, writeJson, Failure } from '../lib/process.mjs';
import { localnetCommand } from '../lib/localnet-isolation.mjs';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';
import { existsSync, mkdtempSync, rmSync, readFileSync, readlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
// Both phases must end before the 45 minute job limit, so a hang fails here with
// its output instead of being cancelled without a report.
const buildTimeoutMs = 25 * 60_000;
const localnetTimeoutMs = 15 * 60_000;
const phase = (name, started) =>
  console.log(`[solana] ${name} finished after ${Math.round((Date.now() - started) / 1000)} s`);
const cwd = resolve(root, 'chain/solana'),
  home = mkdtempSync(resolve(tmpdir(), 'silicium-localnet-'));
const binary = resolve(cwd, 'target/deploy/solana_layer.so');
const digest = () => createHash('sha256').update(readFileSync(binary)).digest('hex');
try {
  const wallet = resolve(home, 'wallet.json');
  run(['solana-keygen', 'new', '--no-bip39-passphrase', '--silent', '--outfile', wallet]);
  const pubkey = run(['solana-keygen', 'pubkey', wallet]).stdout.trim();
  const env = { ANCHOR_WALLET: wallet, RUSTUP_TOOLCHAIN: '1.89.0' };
  console.log('[solana] anchor build (SBF)');
  const built = Date.now();
  const build = runLive(['anchor', 'build', '--provider.cluster', 'localnet'], {
    cwd,
    env,
    timeout: buildTimeoutMs,
  });
  phase('anchor build', built);
  if (build.timedOut)
    throw new Failure(`anchor build timed out after ${buildTimeoutMs / 60_000} min`, 4);
  if (build.status) throw new Failure(`anchor build failed (${build.status})`);
  if (!existsSync(binary)) throw new Failure('SBF build missing');
  const before = digest(),
    idl = readJson(resolve(cwd, 'target/idl/solana_layer.json'));
  const declared = readFileSync(resolve(cwd, 'programs/solana-layer/src/lib.rs'), 'utf8').match(
    /declare_id!\("([1-9A-HJ-NP-Za-km-z]+)"\)/,
  )?.[1];
  if (!declared || idl.address !== declared) throw new Failure('IDL/program address mismatch');
  const config = resolve(home, 'qualification.json');
  writeJson(config, {
    home,
    pubkey,
    declared,
    binary,
    before,
    parent_namespace: readlinkSync('/proc/self/ns/net'),
    runtime_path: process.env.PATH,
  });
  const probe = run(
    ['unshare', '--user', '--map-root-user', '--net', '--pid', '--fork', '--mount-proc', 'true'],
    { allowFailure: true, timeout: 10_000 },
  );
  const command = localnetCommand({
    userNamespaces: probe.status === 0,
    githubActions: process.env.GITHUB_ACTIONS === 'true',
    uid: process.getuid(),
    gid: process.getgid(),
    node: process.execPath,
    script: resolve(root, 'tools/tasks/solana-localnet.mjs'),
    config,
  });
  console.log('[solana] isolated localnet qualification');
  const started = Date.now();
  const result = runLive(command, { cwd: root, timeout: localnetTimeoutMs });
  phase('localnet qualification', started);
  if (result.timedOut)
    throw new Failure(`Isolated localnet timed out after ${localnetTimeoutMs / 60_000} min`, 4);
  if (digest() !== before) throw new Failure('Program changed between build and qualification');
  if (result.status) throw new Failure('Isolated Anchor localnet qualification failed');
  console.log(`Qualified SBF sha256: ${before}`);
} finally {
  rmSync(home, { recursive: true, force: true });
}
