/** Raw input size bounds zipped artifacts conservatively, before each upload. */
import { readdirSync, statSync, realpathSync } from 'node:fs';
import { resolve, relative, isAbsolute } from 'node:path';
import { root, Failure } from '../lib/process.mjs';
export function treeSize(path) {
  const boundary = realpathSync(path);
  const visit = (current, ancestors) => {
    const actual = realpathSync(current),
      rel = relative(boundary, actual);
    if (isAbsolute(rel) || rel === '..' || rel.startsWith('../') || rel.startsWith('..\\'))
      throw new Failure('Artifact symlink escapes its root');
    if (ancestors.has(actual)) throw new Failure('Artifact symlink cycle');
    const entry = statSync(actual);
    if (entry.isFile()) return entry.size;
    if (!entry.isDirectory()) throw new Failure('Unexpected artifact input type');
    const next = new Set([...ancestors, actual]);
    return readdirSync(current).reduce((n, file) => n + visit(resolve(current, file), next), 0);
  };
  return visit(path, new Set());
}
if (process.argv[1]?.endsWith('/artifact-size.mjs')) {
  const path = process.argv[2],
    limit = Number(process.argv[3]);
  if (!path || !Number.isSafeInteger(limit) || limit < 1)
    throw new Failure('Expected PATH LIMIT_BYTES', 2);
  const size = treeSize(resolve(root, path));
  if (size > limit)
    throw new Failure(`Artifact exceeds its reserved budget: ${size} > ${limit}`, 4);
  console.log(
    JSON.stringify({
      schema_version: 1,
      path,
      size_bytes: size,
      limit_bytes: limit,
      status: 'success',
    }),
  );
}
