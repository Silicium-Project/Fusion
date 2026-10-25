/** Fetch a versioned upstream tool and verify its published SHA-256 before extraction. */
import { createHash } from 'node:crypto';
import { mkdirSync, writeFileSync, chmodSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { api } from './github.mjs';
import { run, Failure } from './process.mjs';
export async function installTool({ repository, version, name, suffix, destination }) {
  const executable=resolve(destination,name+(process.platform==='win32'?'.exe':''));
  if(existsSync(executable))return executable;
  const release=api(`repos/${repository}/releases/tags/v${version}`);
  const asset=release.assets.find(x=>x.name.endsWith(suffix));
  const sums=release.assets.find(x=>/checksums/i.test(x.name));
  if(!asset||!sums)throw new Failure(`Missing signed-release asset/checksum listing for ${name}`,2);
  const fetchBytes=async url=>{const response=await fetch(url);if(!response.ok)throw new Failure(`Tool download failed: ${response.status}`,4);return Buffer.from(await response.arrayBuffer());};
  const checksums=(await fetchBytes(sums.browser_download_url)).toString('utf8');
  const expected=checksums.split('\n').find(l=>l.trim().split(/\s+/).at(-1)?.replace(/^\*/,'')===asset.name)?.trim().split(/\s+/)[0];
  const bytes=await fetchBytes(asset.browser_download_url);
  if(!expected||createHash('sha256').update(bytes).digest('hex')!==expected)throw new Failure(`Checksum mismatch for ${name}`,3);
  mkdirSync(destination,{recursive:true});const archive=resolve(destination,asset.name);writeFileSync(archive,bytes);
  run(['tar','-xzf',archive,'-C',destination,name+(process.platform==='win32'?'.exe':'')]);chmodSync(executable,0o755);
  return executable;
}
