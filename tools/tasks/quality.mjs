/** Portable repository checks. Historical documentation is retained as an explicit archive. */
import { existsSync, readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { git, root, Failure, run } from '../lib/process.mjs';

const files = git('ls-files', '-z').split('\0').filter(Boolean);
const failures = [];
for (const file of files) {
  if (/(^|\/)(node_modules|target|dist|\.silicium|ledger|\.anchor)\//.test(file))
    failures.push(`Generated runtime state tracked: ${file}`);
  if (/\.(pfx|p12|key)$/.test(file) || /(^|\/)[^/]*keypair\.json$/.test(file))
    failures.push(`Private key-shaped file tracked: ${file}`);
}
const mode = process.argv[2] ?? 'repository';
if (mode === 'docs') {
  const canonical = [
    ...new Set([
      'README.md',
      'CONTRIBUTING.md',
      'AGENTS.md',
      'contracts/README.md',
      ...files.filter(
        (file) =>
          file.startsWith('docs/') && !file.startsWith('docs/archive/') && file.endsWith('.md'),
      ),
      ...[
        'apps/web',
        'apps/api',
        'apps/node',
        'network',
        'chain/solana',
        'chain/sdk',
        'infra',
      ]
        .flatMap((path) => [path + '/AGENTS.md', path + '/README.md'])
        .filter((file) => existsSync(resolve(root, file))),
    ]),
  ];
  for (const file of canonical) {
    if (!existsSync(resolve(root, file))) {
      failures.push(`Missing canonical documentation: ${file}`);
      continue;
    }
    const text = readFileSync(resolve(root, file), 'utf8');
    for (const match of text.matchAll(/\[[^\]]*\]\(([^)]+)\)/g)) {
      const link = match[1].split('#')[0];
      if (!link || /^(https?:|mailto:)/.test(link)) continue;
      if (!existsSync(resolve(dirname(resolve(root, file)), decodeURIComponent(link))))
        failures.push(`${file}: missing link ${link}`);
    }
  }
} else if (mode === 'go-format') {
  const result = run(['gofmt', '-l', '.'], { cwd: resolve(root, 'apps/api') });
  if (result.stdout.trim()) failures.push(`gofmt required:\n${result.stdout}`);
} else if (mode === 'typescript') {
  run(['npm', 'exec', '--', 'nuxi', 'typecheck'], { cwd: resolve(root, 'apps/web') });
} else if (mode !== 'repository') throw new Failure(`Unknown quality mode ${mode}`, 2);
if (failures.length) throw new Failure(failures.join('\n'));
console.log(`${mode}: passed`);
