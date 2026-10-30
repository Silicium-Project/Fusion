/** Runs only inside the disposable network/PID namespace prepared by solana.mjs. */
import { run, runLive, root, readJson, Failure } from '../lib/process.mjs';
import { assertIsolatedLocalnet } from '../lib/localnet-isolation.mjs';
import { resolve } from 'node:path';
import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, readFileSync, readlinkSync, openSync, closeSync } from 'node:fs';
import { networkInterfaces } from 'node:os';
import { createServer } from 'node:net';
const config = readJson(resolve(process.argv[2]));
assertIsolatedLocalnet(
  config.parent_namespace,
  readlinkSync('/proc/self/ns/net'),
  networkInterfaces(),
);
process.env.PATH = config.runtime_path;
const { home, pubkey, declared, binary, before } = config;
const cwd = resolve(root, 'chain/solana'),
  wallet = resolve(home, 'wallet.json');
const env = { ANCHOR_WALLET: wallet, RUSTUP_TOOLCHAIN: '1.89.0' };
const digest = () => createHash('sha256').update(readFileSync(binary)).digest('hex');
if (digest() !== before) throw new Failure('SBF changed before isolated tests');
// Shorter than the 15 minute localnet limit of solana.mjs, so the validator log is printed.
const testTimeoutMs = 12 * 60_000;
let validator, log;
async function freePort() {
  const server = createServer();
  await new Promise((ok, bad) => {
    server.once('error', bad).listen(0, '127.0.0.1', ok);
  });
  const port = server.address().port;
  await new Promise((ok) => {
    server.close(ok);
  });
  return port;
}
try {
  const port = await freePort(),
    faucet = await freePort();
  const url = `http://127.0.0.1:${port}`;
  log = openSync(resolve(home, 'validator.log'), 'w', 0o600);
  validator = spawn(
    'solana-test-validator',
    [
      '--reset',
      '--quiet',
      '--ledger',
      resolve(home, 'ledger'),
      '--rpc-port',
      String(port),
      '--faucet-port',
      String(faucet),
      '--bind-address',
      '127.0.0.1',
      '--mint',
      pubkey,
      '--bpf-program',
      declared,
      binary,
    ],
    { cwd, stdio: ['ignore', log, log] },
  );
  validator.on('error', () => {});
  let ready = false;
  for (let i = 0; i < 90; i++) {
    if (validator.exitCode !== null || validator.signalCode)
      throw new Failure('Disposable validator stopped before readiness');
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'getHealth' }),
        signal: AbortSignal.timeout(1000),
      });
      ready = (await response.json()).result === 'ok';
    } catch {}
    if (ready) break;
    await new Promise((ok) => {
      setTimeout(ok, 500);
    });
  }
  if (!ready) throw new Failure('Disposable validator did not become ready');
  const result = runLive(
    [
      'anchor',
      'test',
      '--skip-build',
      '--skip-deploy',
      '--skip-local-validator',
      '--provider.cluster',
      url,
      '--provider.wallet',
      wallet,
    ],
    { cwd, env: { ...env, ANCHOR_PROVIDER_URL: url }, timeout: testTimeoutMs },
  );
  if (result.timedOut)
    throw new Failure(`anchor test timed out after ${testTimeoutMs / 60_000} min`, 4);
  if (digest() !== before) throw new Failure('Program changed between build and qualification');
  if (result.status) throw new Failure('Anchor localnet qualification failed');
  console.log(`Qualified SBF sha256: ${before}`);
} catch (error) {
  for (const path of [resolve(home, 'validator.log'), resolve(home, 'ledger/validator.log')])
    if (existsSync(path))
      process.stderr.write(
        `Disposable validator diagnostic (bounded):\n${readFileSync(path, 'utf8').slice(-16_384).replaceAll(home, '<localnet>')}\n`,
      );
  throw error;
} finally {
  if (validator && validator.exitCode === null) {
    validator.kill('SIGTERM');
    await new Promise((ok) => {
      validator.once('exit', ok);
      setTimeout(() => {
        validator.kill('SIGKILL');
        ok();
      }, 5000).unref();
    });
  }
  if (log !== undefined) closeSync(log);
}
