/** Execute registered commands locally or in CI with the same evidence format. */
import { performance } from 'node:perf_hooks';
import { existsSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { registry, makePlan } from './planner.mjs';
import { run, git, inside, root, Failure, readJson, writeJson } from './process.mjs';

export function countTests(text, format) {
  if (format === 'node') return Number([...text.matchAll(/# tests (\d+)/g)].at(-1)?.[1] ?? 0);
  if (format === 'vitest')
    return [...text.matchAll(/Tests\s+(\d+) passed/g)].reduce((n, x) => n + Number(x[1]), 0);
  if (format === 'rust')
    return [...text.matchAll(/test result: ok\. (\d+) passed/g)].reduce(
      (n, x) => n + Number(x[1]),
      0,
    );
  if (format === 'pytest') return Number(text.match(/(?:^|\s)(\d+) passed(?:,|\s|$)/)?.[1] ?? 0);
  if (format === 'playwright') return Number(text.match(/(?:^|\s)(\d+) passed\s*\(/)?.[1] ?? 0);
  if (format === 'anchor') return Number(text.match(/(\d+) passing/)?.[1] ?? 0);
  if (format === 'go')
    return text.split('\n').filter((l) => {
      try {
        return JSON.parse(l).Action === 'pass' && Boolean(JSON.parse(l).Test);
      } catch {
        return false;
      }
    }).length;
  return 0;
}
export function executeSuite(id, { plan, output } = {}) {
  const config = registry(),
    suite = config.suites[id];
  if (!suite) throw new Failure(`Unknown suite ${id}`, 2);
  if (suite.runner.startsWith('windows') && process.platform !== 'win32')
    throw new Failure(`${id} requires Windows`, 2);
  const currentPlan = plan ?? makePlan({ paths: [] });
  const sha = git('rev-parse', 'HEAD');
  if (sha !== currentPlan.source_sha)
    throw new Failure('Checkout does not match qualification plan', 2);
  const report = {
    schema_version: 1,
    suite: id,
    source_sha: sha,
    policy_digest: currentPlan.policy_digest,
    toolchain_policy: readJson(resolve(root, 'tools/config/toolchains.json')),
    execution_platform: {
      node: process.version,
      os: process.platform,
      arch: process.arch,
      rustup_toolchain: process.env.RUSTUP_TOOLCHAIN ?? null,
    },
    dirty: Boolean(git('status', '--porcelain', '--untracked-files=normal')),
    started_at: new Date().toISOString(),
    status: 'running',
    steps: [],
  };
  const cacheSources = {
    npm: ['tooling', 'web', 'node-ui', 'solana'].includes(id),
    rust: [
      'network',
      'network-wasm',
      'network-integration',
      'node-native',
      'node-windows',
      'solana',
    ].includes(id),
    go: id === 'api',
  };
  const cacheEnabled = process.env.SILICIUM_CACHE_ENABLED;
  report.cache_observations = {
    enabled: cacheEnabled === 'true' ? true : cacheEnabled === 'false' ? false : null,
    sources: Object.fromEntries(
      Object.entries(cacheSources).map(([name, applicable]) => [
        name,
        cacheEnabled === 'true' && applicable
          ? process.env[`SILICIUM_CACHE_${name.toUpperCase()}`] === 'true'
          : null,
      ]),
    ),
  };
  const start = performance.now();
  for (const step of suite.steps) {
    const t = performance.now();
    const result = run(step.command, {
      cwd: inside(step.cwd ?? '.'),
      env: { NO_COLOR: '1', CARGO_TERM_COLOR: 'never', ...step.env },
      allowFailure: true,
      timeout: suite.timeout_minutes * 60_000,
    });
    process.stdout.write(result.stdout);
    process.stderr.write(result.stderr);
    const text = result.stdout + result.stderr;
    const count = step.kind === 'test' ? countTests(text, step.format) : null;
    const exit = result.status || (step.kind === 'test' && count < 1 ? 1 : 0);
    report.steps.push({
      command: step.command,
      env: step.env ?? {},
      cwd: step.cwd ?? '.',
      kind: step.kind,
      exit_code: exit,
      tests_executed: count,
      duration_ms: Math.round(performance.now() - t),
      error: result.error,
    });
    if (exit) {
      report.status = 'failure';
      break;
    }
  }
  if (report.status === 'running') report.status = 'success';
  report.dirty_after = Boolean(git('status', '--porcelain', '--untracked-files=normal'));
  if (!report.dirty && report.dirty_after) {
    report.status = 'failure';
    report.failure_kind = 'source_mutation';
    report.error =
      'Validation modified tracked or non-ignored source files; inspect the diff and qualify the resulting commit.';
  }
  report.duration_ms = Math.round(performance.now() - start);
  report.finished_at = new Date().toISOString();
  writeJson(output ?? resolve(root, '.artifacts/reports', `${id}.json`), report);
  return report;
}
