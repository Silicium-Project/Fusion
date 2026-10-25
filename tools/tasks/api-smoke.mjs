/** Exercise the already built API with a disposable SQLite database and no network or chain dependency. */
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { randomBytes, createHash } from 'node:crypto';
import { mkdtempSync, readFileSync, existsSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';
import { createServer } from 'node:net';
import { root, Failure } from '../lib/process.mjs';

const binary = resolve(root, '.artifacts/build/api/silicium-api');
if (!existsSync(binary))
  throw new Failure('Build the API through its registered suite before this smoke test', 2);
const socket = createServer();
await new Promise((ok, bad) => {
  socket.once('error', bad).listen(0, '127.0.0.1', ok);
});
const port = socket.address().port;
await new Promise((ok) => {
  socket.close(ok);
});
const folder = mkdtempSync(resolve(tmpdir(), 'silicium-api-smoke-'));
let logs = '',
  startupError;
const child = spawn(binary, [], {
  cwd: resolve(root, 'apps/api'),
  env: {
    PATH: process.env.PATH,
    HOST: '127.0.0.1',
    PORT: String(port),
    DATABASE_DRIVER: 'sqlite',
    DATABASE_URL: '',
    SQLITE_PATH: resolve(folder, 'site.db'),
    JWT_SECRET_KEY: randomBytes(32).toString('hex'),
    SILICIUM_RELEASE_CHANNEL: 'dev',
    SILICIUM_RELEASE_VERSION: '0.0.0-dev.1',
    SILICIUM_RELEASE_BUILD: 'local-smoke',
    SILICIUM_RELEASE_ID: 'disposable-smoke',
    SILICIUM_SITE_STORAGE_DIR: resolve(folder, 'jobs'),
    SILICIUM_WORKLOAD_STORAGE_DIR: resolve(folder, 'runtime'),
    SILICIUM_NETWORK_ROOT: resolve(folder, 'network'),
    SILICIUM_NODE_API_URL: 'http://127.0.0.1:9',
    SILICIUM_DEVNET_TRACE: '0',
    SILICIUM_SOLANA_PAYMENTS_ENABLED: '0',
    SILICIUM_CATALOG_SYNC: '0',
    SILICIUM_SOLANA_WALLET: resolve(folder, 'nonexistent-wallet.json'),
  },
  stdio: ['ignore', 'pipe', 'pipe'],
});
const done = new Promise((ok) => {
  child.once('exit', ok);
});
child.once('error', (error) => {
  startupError = error;
});
for (const stream of [child.stdout, child.stderr])
  stream.on('data', (data) => {
    logs = (logs + data.toString()).slice(-8192);
  });
const request = (path) =>
  fetch(`http://127.0.0.1:${port}${path}`, { signal: AbortSignal.timeout(1500) });
try {
  let ready = false;
  for (let i = 0; i < 100; i++) {
    if (startupError || child.exitCode !== null || child.signalCode)
      throw new Failure('Disposable API stopped before readiness');
    try {
      const response = await request('/health');
      ready = response.status === 200 && (await response.text()) === 'ok\n';
    } catch {}
    if (ready) break;
    await new Promise((ok) => {
      setTimeout(ok, 100);
    });
  }
  assert.ok(ready, 'API readiness timed out');
  console.log('ok 1 - the built API starts against a disposable SQLite database');
  const version = await request('/version');
  assert.equal(version.status, 200);
  const identity = await version.json();
  assert.equal(identity.release_channel, 'dev');
  assert.equal(identity.release_build, 'local-smoke');
  assert.equal(identity.release_id, 'disposable-smoke');
  console.log('ok 2 - runtime identity matches the explicit candidate metadata');
  const spec = await request('/docs/openapi.yaml');
  assert.equal(spec.status, 200);
  const hash = (bytes) => createHash('sha256').update(bytes).digest('hex');
  assert.equal(
    hash(Buffer.from(await spec.arrayBuffer())),
    hash(readFileSync(resolve(root, 'contracts/http/api.openapi.yaml'))),
  );
  console.log('ok 3 - the served contract is the shared versioned OpenAPI source');
  assert.equal((await request('/user/devices')).status, 401);
  assert.ok(existsSync(resolve(folder, 'site.db')));
  console.log('ok 4 - account devices remain inaccessible without authentication');
  console.log('1..4\n# tests 4\n# pass 4');
} catch (error) {
  process.stderr.write(logs.replaceAll(folder, '<disposable-api>'));
  throw error;
} finally {
  if (child.pid && child.exitCode === null && !child.signalCode) {
    child.kill('SIGTERM');
    await Promise.race([
      done,
      new Promise((ok) => {
        setTimeout(() => {
          child.kill('SIGKILL');
          ok();
        }, 5000).unref();
      }),
    ]);
  }
  rmSync(folder, { recursive: true, force: true });
}
