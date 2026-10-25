/** Gitleaks alone does not recognize Solana CLI arrays. Check Ed25519 consistency without revealing bytes. */
import { createPrivateKey, createPublicKey } from 'node:crypto';
import { run, Failure } from '../lib/process.mjs';
export function isSolanaKeypair(value) {
  if (
    !Array.isArray(value) ||
    value.length !== 64 ||
    !value.every((n) => Number.isInteger(n) && n >= 0 && n <= 255)
  )
    return false;
  const seed = Buffer.from(value.slice(0, 32));
  const key = createPrivateKey({
    key: Buffer.concat([Buffer.from('302e020100300506032b657004220420', 'hex'), seed]),
    format: 'der',
    type: 'pkcs8',
  });
  return createPublicKey(key)
    .export({ format: 'der', type: 'spki' })
    .subarray(-32)
    .equals(Buffer.from(value.slice(32)));
}
export function findKeypairs(text) {
  const pattern = /\[\s*(?:\d{1,3}\s*,\s*){63}\d{1,3}\s*\]/g;
  return [...text.matchAll(pattern)]
    .filter((m) => isSolanaKeypair(JSON.parse(m[0])))
    .map((m) => ({ offset: m.index, length: m[0].length }));
}
if (process.argv[1]?.endsWith('/solana-key-audit.mjs')) {
  const objects = run(['git', 'rev-list', '--objects', '--all']).stdout.trim().split('\n');
  const findings = [];
  for (const object of objects) {
    const space = object.indexOf(' ');
    if (space < 0) continue;
    const sha = object.slice(0, space),
      path = object.slice(space + 1);
    if (/\.(png|ico|jpg|zip|woff2?|AppImage|exe|rpm|deb)$/i.test(path)) continue;
    const r = run(['git', 'cat-file', 'blob', sha], { allowFailure: true });
    if (r.status) continue;
    for (const location of findKeypairs(r.stdout))
      findings.push({ blob_sha: sha, path, ...location, value: 'REDACTED' });
  }
  console.log(
    JSON.stringify(
      { schema_version: 1, status: findings.length ? 'failure' : 'success', findings },
      null,
      2,
    ),
  );
  if (findings.length)
    throw new Failure(
      'A valid Solana keypair exists in reachable history; revoke or classify before publication',
    );
}
