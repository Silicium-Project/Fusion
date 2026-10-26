/** Pin every AppImage helper by content hash, including upstream scripts normally fetched from master. */
import { resolve } from 'node:path';
import { homedir } from 'node:os';
import { readFileSync, writeFileSync, mkdirSync, chmodSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { root, readJson, Failure } from '../lib/process.mjs';
const cache = resolve(process.env.XDG_CACHE_HOME ?? resolve(homedir(), '.cache'), 'tauri');
mkdirSync(cache, { recursive: true });
for (const tool of readJson(resolve(root, 'tools/config/appimage-tools.json')).tools) {
  const response = await fetch(tool.url, { signal: AbortSignal.timeout(120000) });
  if (!response.ok)
    throw new Failure(`AppImage helper unavailable: ${tool.name} HTTP ${response.status}`);
  const bytes = Buffer.from(await response.arrayBuffer());
  if (createHash('sha256').update(bytes).digest('hex') !== tool.sha256)
    throw new Failure(`AppImage helper checksum mismatch: ${tool.name}`);
  const path = resolve(cache, tool.name);
  writeFileSync(path, bytes);
  chmodSync(path, 0o755);
}
console.log('AppImage helpers match the reviewed content hashes.');
