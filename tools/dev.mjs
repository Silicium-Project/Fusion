#!/usr/bin/env node
/** One entry point for contributors, agents and Actions; see dev help. */
import { readdirSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { parseArgs, print, readJson, writeJson, root, run, Failure } from './lib/process.mjs';
import { makePlan, policyFromBase, combinePlans, registry } from './lib/planner.mjs';
import { executeSuite } from './lib/runner.mjs';
import { validateGate } from './lib/gate.mjs';
import { doctor } from './lib/doctor.mjs';
import { api, repository, publicMetadata } from './lib/github.mjs';
import { startIssue, acceptIssue } from './lib/project.mjs';
import { releasePlan, requestDeploy } from './lib/release.mjs';
import { diagnosticRequest } from './lib/operations.mjs';

const commands = [
  {
    command: 'doctor',
    effect: 'read',
    usage: 'doctor --profile tooling|web|api|node|network|solana|delivery|all',
  },
  { command: 'capabilities', effect: 'read', usage: 'capabilities --json' },
  {
    command: 'ci plan',
    effect: 'read',
    usage: 'ci plan --base origin/main --head HEAD --output .artifacts/plan.json',
  },
  {
    command: 'ci gate',
    effect: 'read',
    usage: 'ci gate --plan .artifacts/plan.json --reports .artifacts/reports',
  },
  { command: 'ci inspect', effect: 'read', usage: 'ci inspect --run ID' },
  { command: 'check', effect: 'local validation', usage: 'check --changed --base origin/main' },
  {
    command: 'test',
    effect: 'local validation',
    usage: 'test --suite ID [--plan .artifacts/plan.json]',
  },
  {
    command: 'build',
    effect: 'local build',
    usage: 'build --component web|api|network|node|solana|sdk',
  },
  {
    command: 'format',
    effect: 'read; modifies source files only with --write',
    usage: 'format [--write]',
  },
  {
    command: 'issue start',
    effect: 'GitHub Project write with --apply',
    usage: 'issue start ISSUE_URL [--apply]',
  },
  {
    command: 'issue accept',
    effect: 'issue closure with human approval',
    usage: 'issue accept ISSUE_URL --evidence URL --human-approved [--apply]',
  },
  {
    command: 'release plan',
    effect: 'read',
    usage: 'release plan --channel dev|prod --version VERSION [--run ID]',
  },
  {
    command: 'deploy request',
    effect: 'workflow dispatch with --apply',
    usage: 'deploy request --manifest FILE --environment dev|prod [--apply]',
  },
  {
    command: 'ops diagnose',
    effect: 'read-only host observations through workflow dispatch with --apply',
    usage: 'ops diagnose --environment dev|prod [--apply]',
  },
];
async function main() {
  const { args, options: o } = parseArgs(process.argv.slice(2));
  const [command = 'help', subcommand, value] = args;
  const output = (v) => print(v, Boolean(o.json));
  if (command === 'help' || command === 'capabilities')
    return output({
      schema_version: 1,
      commands: commands.map((c) => ({
        ...c,
        availability:
          c.command.startsWith('deploy') ||
          c.command.startsWith('issue') ||
          c.command.startsWith('ops')
            ? 'configuration_required'
            : 'available',
      })),
      features: {
        validation: 'available',
        signed_delivery: 'experimental',
        project_automation: 'configuration_required',
        worker_rolling_update: 'planned',
      },
      suites: Object.keys(registry().suites),
      documentation: 'docs/ai/README.md',
    });
  if (command === 'doctor') {
    const result = doctor(o);
    output(result);
    process.exitCode = result.status === 'success' ? 0 : 2;
    return;
  }
  if (command === 'ci' && subcommand === 'plan') {
    let plan = makePlan(o);
    if (o.base) {
      const previous = policyFromBase(o.base);
      if (previous)
        plan = combinePlans(plan, makePlan({ ...o, paths: plan.paths, config: previous }));
    }
    if (o.output) writeJson(resolve(o.output), plan);
    return output(plan);
  }
  if (command === 'ci' && subcommand === 'gate') {
    const plan = readJson(resolve(o.plan ?? '.artifacts/plan.json'));
    const dir = resolve(o.reports ?? '.artifacts/reports');
    const files = readdirSync(dir, { recursive: true }).filter((x) => x.endsWith('.json'));
    const reports = files.map((x) => readJson(resolve(dir, x))).filter((x) => x.suite);
    const result = validateGate(plan, reports, { expectedSha: o.sha ?? plan.source_sha });
    output(result);
    process.exitCode = result.status === 'success' ? 0 : 1;
    return;
  }
  if (command === 'ci' && subcommand === 'inspect') {
    if (!/^[1-9][0-9]*$/.test(String(o.run))) throw new Failure('Provide --run ID', 2);
    return output({
      schema_version: 1,
      run: publicMetadata(api(`repos/${repository}/actions/runs/${o.run}`)),
      jobs: api(`repos/${repository}/actions/runs/${o.run}/jobs?per_page=100`),
    });
  }
  if (command === 'test') {
    if (!o.suite) throw new Failure('Provide --suite; see capabilities', 2);
    const report = executeSuite(o.suite, {
      plan: o.plan ? readJson(resolve(o.plan)) : undefined,
      output: o.output,
    });
    output(report);
    process.exitCode = report.status === 'success' ? 0 : 1;
    return;
  }
  if (command === 'check') {
    const plan = makePlan(o);
    writeJson(resolve(root, '.artifacts/plan.json'), plan);
    for (const suite of plan.suites) {
      const result = executeSuite(suite, { plan });
      if (result.status !== 'success') {
        output(result);
        process.exitCode = 1;
        return;
      }
    }
    return output({ status: 'success', suites: plan.suites });
  }
  if (command === 'build') {
    const builds = {
      web: { cwd: 'apps/web', command: ['npm', 'run', 'build'] },
      api: {
        cwd: 'apps/api',
        command: [
          'go',
          'build',
          '-trimpath',
          '-o',
          '../../.artifacts/build/api/silicium-api',
          './cmd',
        ],
      },
      network: {
        cwd: 'network',
        command: [
          'cargo',
          'build',
          '--release',
          '--locked',
          '-p',
          'p2p_node',
          '-p',
          'compute_daemon',
          '-p',
          'silicium-raytracer',
        ],
      },
      node: { cwd: 'apps/node', command: ['npm', 'run', 'build'] },
      sdk: { cwd: 'packages/solana-sdk', command: ['npm', 'run', 'build'] },
      solana: {
        cwd: 'chain/solana',
        command: ['anchor', 'build', '--provider.cluster', 'localnet'],
      },
    };
    const build = builds[o.component];
    if (!build) throw new Failure('Unknown --component', 2);
    const r = run(build.command, { cwd: resolve(root, build.cwd), timeout: 3_600_000 });
    process.stdout.write(r.stdout);
    process.stderr.write(r.stderr);
    return output({ schema_version: 1, component: o.component, status: 'success' });
  }
  if (command === 'format') {
    const result = run(['node', 'tools/quality/run.mjs', o.write ? 'write' : 'check'], {
      timeout: 600_000,
    });
    process.stdout.write(result.stdout);
    process.stderr.write(result.stderr);
    return output({
      schema_version: 1,
      operation: 'format',
      status: 'success',
      write: Boolean(o.write),
    });
  }
  if (command === 'issue' && subcommand === 'start')
    return output(startIssue(value, Boolean(o.apply)));
  if (command === 'issue' && subcommand === 'accept')
    return output(
      acceptIssue(value, o.evidence, {
        apply: Boolean(o.apply),
        humanApproved: Boolean(o['human-approved']),
      }),
    );
  if (command === 'release' && subcommand === 'plan') return output(releasePlan(o));
  if (command === 'deploy' && subcommand === 'request')
    return output(
      requestDeploy(o.manifest, { environment: o.environment, apply: Boolean(o.apply) }),
    );
  if (command === 'ops' && subcommand === 'diagnose')
    return output(diagnosticRequest(o.environment, Boolean(o.apply)));
  throw new Failure('Unknown command; run ./dev help', 2);
}
main().catch((error) => {
  print({
    schema_version: 1,
    status: 'failure',
    error: error.message,
    exit_code: error.exitCode ?? 1,
  });
  process.exitCode = error.exitCode ?? 1;
});
