/** The official release archive replaces an installer whose secondary download failed. */
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import { existsSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { root, readJson, run, Failure } from '../lib/process.mjs';
export async function installSolana(directory, version) {
  const pin = readJson(resolve(root, 'tools/config/solana-tools.json'));
  if (pin.version !== version)
    throw new Failure('Solana archive and toolchain version must be reviewed together', 2);
  mkdirSync(directory, { recursive: true });
  const bin = resolve(directory, 'solana-release/bin');
  if (!existsSync(resolve(bin, 'solana'))) {
    const response = await fetch(pin.url, { signal: AbortSignal.timeout(120_000) });
    if (!response.ok)
      throw new Failure(`Official Solana archive download failed: HTTP ${response.status}`, 4);
    const bytes = Buffer.from(await response.arrayBuffer());
    if (createHash('sha256').update(bytes).digest('hex') !== pin.sha256)
      throw new Failure('Solana archive checksum mismatch', 3);
    const archive = resolve(directory, 'release.tar.bz2');
    writeFileSync(archive, bytes, { mode: 0o600 });
    try {
      run(['tar', '-xjf', archive, '-C', directory], { timeout: 180_000 });
    } finally {
      rmSync(archive, { force: true });
    }
  }
  const actual = run([resolve(bin, 'solana'), '--version']).stdout;
  if (!actual.startsWith(`solana-cli ${version} `))
    throw new Failure('Installed Solana CLI version mismatch', 3);
  return bin;
}
