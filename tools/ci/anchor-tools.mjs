/** Verify the upstream release binary instead of rebuilding the CLI before every program test. */
import { resolve } from 'node:path';
import { existsSync, mkdirSync, writeFileSync, renameSync, rmSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { root, readJson, run, Failure } from '../lib/process.mjs';
import { verifyCachedTool } from '../lib/download.mjs';
export async function installAnchor(directory, version) {
  const pin = readJson(resolve(root, 'tools/config/anchor-tools.json'));
  const source = readJson(resolve(root, 'tools/config/upstreams.json')).anchor;
  if (
    pin.version !== version ||
    pin.source_commit !== source ||
    process.platform !== 'linux' ||
    process.arch !== 'x64'
  )
    throw new Failure(
      'Anchor binary, source revision, version and platform must match the reviewed toolchain',
      2,
    );
  const bin = resolve(directory, 'bin'),
    executable = resolve(bin, 'anchor');
  mkdirSync(bin, { recursive: true });
  if (!existsSync(executable)) {
    const response = await fetch(pin.url, { signal: AbortSignal.timeout(120_000) });
    if (!response.ok)
      throw new Failure(`Pinned Anchor binary unavailable: HTTP ${response.status}`, 4);
    const bytes = Buffer.from(await response.arrayBuffer());
    if (createHash('sha256').update(bytes).digest('hex') !== pin.sha256)
      throw new Failure('Anchor binary checksum mismatch', 3);
    const temporary = resolve(bin, `.anchor-${process.pid}.tmp`);
    try {
      writeFileSync(temporary, bytes, { mode: 0o555 });
      renameSync(temporary, executable);
    } finally {
      rmSync(temporary, { force: true });
    }
  }
  verifyCachedTool(executable, pin.sha256);
  if (run([executable, '--version']).stdout.trim() !== `anchor-cli ${version}`)
    throw new Failure('Anchor binary version mismatch', 3);
  return bin;
}
