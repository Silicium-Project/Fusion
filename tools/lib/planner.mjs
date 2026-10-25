/** Conservative, rename-aware dependency routing; unknown paths require all lanes. */
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { git, readJson, root } from './process.mjs';

export const configPath = resolve(root, 'tools/config/lanes.json');
export const registry = () => readJson(configPath);
export function splitMatrix(plan, config = registry()) {
  const quick = [],
    integration = [];
  for (const row of plan.matrix.include) {
    (config.suites[row.suite]?.phase === 'quick' ? quick : integration).push(row);
  }
  return {
    quick: { include: quick },
    integration: { include: integration },
    integration_count: integration.length,
  };
}
export function parseChanges(raw) {
  const entries = raw.split('\0');
  const paths = [];
  for (let i = 0; i < entries.length && entries[i];) {
    const status = entries[i++];
    if (!/^[ACDMRTUXB][0-9]*$/.test(status))
      throw new Error(`Invalid git change status: ${status}`);
    const count = /^[RC]/.test(status) ? 2 : 1;
    for (let n = 0; n < count; n++) {
      if (!entries[i]) throw new Error('Truncated git name-status output');
      paths.push(entries[i++]);
    }
  }
  return [...new Set(paths)].sort();
}
export function route(paths, config = registry()) {
  const direct = new Set(['tooling', 'docs']);
  const reasons = {};
  let full = false;
  for (const path of paths) {
    if (
      path.startsWith('.github/workflows/') ||
      path.startsWith('tools/') ||
      path.startsWith('contracts/')
    ) {
      full = true;
      reasons[path] = 'shared validation policy or public contract';
      continue;
    }
    if (
      /(^|\/)(README|AGENTS|CONTRIBUTING|SECURITY|CLAUDE)(\.md)?$/i.test(path) ||
      /\.(md|mdx)$/.test(path) ||
      path.startsWith('docs/') ||
      path.startsWith('design/') ||
      path.startsWith('.github/ISSUE_TEMPLATE/') ||
      ['LICENSE', 'NOTICE'].includes(path)
    ) {
      reasons[path] = 'documentation';
      continue;
    }
    if (
      [
        '.gitignore',
        '.gitattributes',
        '.editorconfig',
        '.github/CODEOWNERS',
        '.github/pull_request_template.md',
        'dev',
        'dev.ps1',
        'package.json',
      ].includes(path)
    ) {
      reasons[path] = 'repository tooling';
      continue;
    }
    const found = Object.entries(config.components).filter(([, c]) =>
      c.paths.some((p) => path.startsWith(p)),
    );
    if (!found.length) {
      full = true;
      reasons[path] = 'unknown surface';
    }
    for (const [name] of found) {
      direct.add(name);
      reasons[path] = `component:${name}`;
    }
  }
  if (full) Object.keys(config.components).forEach((x) => direct.add(x));
  const affected = new Set(direct);
  let changed = true;
  while (changed) {
    changed = false;
    for (const [name, component] of Object.entries(config.components)) {
      if (!affected.has(name) && (component.depends_on ?? []).some((d) => affected.has(d))) {
        affected.add(name);
        changed = true;
      }
    }
  }
  const suites = Object.entries(config.suites)
    .filter(([, suite]) => suite.tier === 'pr' && suite.components.some((c) => affected.has(c)))
    .map(([id]) => id)
    .sort();
  return { full, paths, reasons, components: [...affected].sort(), suites };
}
export function makePlan({ base = 'origin/main', head = 'HEAD', paths, config = registry() } = {}) {
  const source = git('rev-parse', '--verify', `${head}^{commit}`);
  let baseSha = '',
    changed = paths;
  if (!changed) {
    try {
      baseSha = git('rev-parse', '--verify', `${base}^{commit}`);
      const ancestor = git('merge-base', baseSha, source);
      changed = parseChanges(
        git('diff', '--name-status', '-z', '--find-renames', ancestor, source, '--'),
      );
    } catch {
      changed = ['__unknown_base__'];
    }
  }
  const selected = route(changed, config);
  const policy = createHash('sha256').update(JSON.stringify(config)).digest('hex');
  const dirty = Boolean(git('status', '--porcelain', '--untracked-files=normal'));
  return {
    schema_version: 1,
    source_sha: source,
    head_sha: process.env.SILICIUM_PR_HEAD || source,
    base_sha: baseSha,
    policy_digest: policy,
    dirty,
    ...selected,
    matrix: {
      include: selected.suites.map((suite) => ({
        suite,
        runner: config.suites[suite].runner,
        timeout: config.suites[suite].timeout_minutes,
      })),
    },
  };
}
export function policyFromBase(base) {
  // Both policies are considered when editing routing rules; a PR cannot narrow its base obligations.
  try {
    return JSON.parse(git('show', `${base}:tools/config/lanes.json`));
  } catch {
    return null;
  }
}
export function combinePlans(plan, previous) {
  if (!previous) return plan;
  const suites = [...new Set([...plan.suites, ...previous.suites])].sort();
  const config = registry();
  for (const id of suites)
    if (!config.suites[id]) throw new Error(`Cannot remove required lane ${id} in its own PR`);
  return {
    ...plan,
    suites,
    matrix: {
      include: suites.map((suite) => ({
        suite,
        runner: config.suites[suite].runner,
        timeout: config.suites[suite].timeout_minutes,
      })),
    },
  };
}
