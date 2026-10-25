/** Verified upstream tools. A corrupted cache is an infrastructure failure, never a silent success. */
import { createHash } from 'node:crypto';
import {
  mkdirSync,
  writeFileSync,
  chmodSync,
  existsSync,
  readFileSync,
  mkdtempSync,
  copyFileSync,
  rmSync,
} from 'node:fs';
import { resolve } from 'node:path';
import { run, root, readJson, Failure } from './process.mjs';
export function verifyCachedTool(path, expected) {
  if (createHash('sha256').update(readFileSync(path)).digest('hex') !== expected) {
    throw new Failure(
      'Tool cache checksum mismatch; remove only the affected .artifacts/tools entry and retry',
      3,
    );
  }
}
export async function installTool({ repository, version, name, destination }) {
  const pin = readJson(resolve(root, 'tools/config/security-tools.json'))[name];
  if (!pin || pin.repository !== repository || pin.version !== version || !/^[a-z]+$/.test(name))
    throw new Failure('Tool is not pinned in security-tools.json', 2);
  if (process.platform !== 'linux' || process.arch !== 'x64')
    throw new Failure('Security qualification requires Linux x86-64', 2);
  const executable = resolve(destination, name);
  if (existsSync(executable)) {
    verifyCachedTool(executable, pin.binary_sha256);
    return executable;
  }
  const response = await fetch(pin.url, { signal: AbortSignal.timeout(30_000) });
  if (!response.ok) throw new Failure(`Tool download failed: HTTP ${response.status}`, 4);
  const bytes = Buffer.from(await response.arrayBuffer());
  if (createHash('sha256').update(bytes).digest('hex') !== pin.sha256)
    throw new Failure(`Archive checksum mismatch for ${name}`, 3);
  mkdirSync(destination, { recursive: true });
  const temporary = mkdtempSync(resolve(destination, 'extract-'));
  try {
    const archive = resolve(temporary, 'tool.tar.gz');
    writeFileSync(archive, bytes, { mode: 0o600 });
    run(['tar', '-xzf', archive, '-C', temporary, name]);
    verifyCachedTool(resolve(temporary, name), pin.binary_sha256);
    copyFileSync(resolve(temporary, name), executable);
    chmodSync(executable, 0o555);
    return executable;
  } finally {
    rmSync(temporary, { recursive: true, force: true });
  }
}
