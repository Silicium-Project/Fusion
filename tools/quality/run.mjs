/** Exact formatter/linter dependencies live in this isolated tools package. */
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { ESLint } from 'eslint';
import * as prettier from 'prettier';
import { root, git, Failure } from '../lib/process.mjs';
const mode = process.argv[2] ?? 'check';
if (!['check', 'write'].includes(mode)) throw new Failure('Expected check or write', 2);
const paths = [
  ...new Set(git('ls-files', '-c', '-o', '--exclude-standard', '-z').split('\0').filter(Boolean)),
].filter(
  (file) =>
    /\.(ts|vue|mjs)$/.test(file) &&
    !file.startsWith('docs/archive/') &&
    !/(^|\/)(dist|target|gen)\//.test(file) &&
    existsSync(resolve(root, file)),
);
const failures = [];
for (const file of paths) {
  const path = resolve(root, file),
    text = readFileSync(path, 'utf8');
  const options = { ...(await prettier.resolveConfig(path)), filepath: path };
  if (mode === 'write') writeFileSync(path, await prettier.format(text, options));
  else if (!(await prettier.check(text, options))) failures.push(file);
}
if (failures.length)
  throw new Failure(
    `Formatting required (${failures.length} files):\n${failures.join('\n')}\nRun ./dev format --write`,
  );
if (mode === 'check') {
  const eslint = new ESLint({
    cwd: root,
    overrideConfigFile: resolve(root, 'tools/quality/eslint.config.mjs'),
  });
  const results = await eslint.lintFiles(paths);
  const formatter = await eslint.loadFormatter('stylish');
  const output = formatter.format(results);
  if (output) console.log(output);
  if (results.some((result) => result.errorCount || result.fatalErrorCount))
    throw new Failure('TypeScript/Vue correctness checks failed');
}
console.log(`${mode}: ${paths.length} maintained TypeScript/Vue/module files`);
