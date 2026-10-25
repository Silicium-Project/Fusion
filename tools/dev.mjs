#!/usr/bin/env node
/** One entry point for contributors, agents and Actions; see dev help. */
import { readdirSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { parseArgs, print, readJson, writeJson, root, run, Failure } from './lib/process.mjs';
import { makePlan, policyFromBase, combinePlans, registry } from './lib/planner.mjs';
import { executeSuite } from './lib/runner.mjs';
import { validateGate } from './lib/gate.mjs';
import { doctor } from './lib/doctor.mjs';
import { startIssue, acceptIssue } from './lib/project.mjs';
import { releasePlan, requestDeploy } from './lib/release.mjs';
import { diagnosticRequest } from './lib/operations.mjs';
import { inspectMetrics } from './lib/metrics.mjs';
import { inspectRun } from './lib/ci-inspect.mjs';
import {
  workspaceStatus,
  initializeWorkspace,
  pinComponent,
  requireSources,
  guardPrivateSources,
  trackedSources,
  workspaceConfig,
} from './lib/workspace.mjs';
import { prepareComponent } from './lib/component.mjs';

const commands = [
  { command: 'workspace status', effect: 'read', usage: 'workspace status --json' },
  {
    command: 'workspace verify',
    effect: 'read',
    usage: 'workspace verify [--materialized] --json',
  },
  {
    command: 'workspace init',
    effect: 'private source checkout with --apply',
    usage: 'workspace init [--component ID] [--apply]',
  },
  {
    command: 'workspace pin',
    effect: 'component checkout and staged pin with --apply',
    usage: 'workspace pin --component ID --revision SHA [--apply]',
  },
  {
    command: 'component',
    effect: 'component qualification in a separate local composition',
    usage:
      'component --component ID --source PATH doctor|prepare|test|check|build [--suite ID] [--destination PATH] [--apply]',
  },
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
  {
    command: 'ci inspect',
    effect: 'read',
    usage: 'ci inspect --run ID [--repository Silicium-Project/Integration]',
  },
  { command: 'ci metrics', effect: 'read', usage: 'ci metrics [--limit 20] --json' },
  {
    command: 'ci authorize-private',
    effect: 'bounded Actions authorization with --apply; no delivery',
    usage: 'ci authorize-private [--head SHA] [--minutes 180] [--apply]',
  },
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
        workspace: 'available',
        private_integration: 'configuration_required',
        validation: 'available',
        signed_delivery: 'configuration_required',
        project_automation: 'configuration_required',
        worker_rolling_update: 'planned',
      },
      suites: Object.keys(registry().suites),
      documentation: 'docs/ai/README.md',
    });
  if (command === 'workspace') {
    let result;
    if (subcommand === 'files') return output(trackedSources());
    if (subcommand === 'status' || subcommand === 'verify')
      result = workspaceStatus({ materialized: Boolean(o.materialized) });
    else if (subcommand === 'init')
      result = initializeWorkspace({ component: o.component, apply: Boolean(o.apply) });
    else if (subcommand === 'pin')
      result = pinComponent({
        component: o.component,
        revision: o.revision,
        apply: Boolean(o.apply),
      });
    else throw new Failure('Unknown workspace operation', 2);
    output(result);
    process.exitCode = result.status === 'blocked' ? 2 : 0;
    return;
  }
  if (command === 'component') {
    if (subcommand === 'doctor') {
      const result = doctor({ profile: o.component });
      output(result);
      process.exitCode = result.status === 'success' ? 0 : 2;
      return;
    }
    if (!['prepare', 'test', 'check', 'build'].includes(subcommand))
      throw new Failure('Unknown component operation', 2);
    const prepared = prepareComponent({
      component: o.component,
      source: o.source,
      destination: o.destination,
      expectedRevision: o.revision,
      apply: subcommand !== 'prepare' || Boolean(o.apply),
    });
    if (subcommand === 'prepare') return output(prepared);
    const cli = resolve(prepared.destination, 'tools/dev.mjs');
    if (subcommand === 'build') {
      const result = run(['node', cli, 'build', '--component', o.component], {
        cwd: prepared.destination,
        timeout: 3_600_000,
      });
      process.stdout.write(result.stdout);
      return;
    }
    const config = workspaceConfig();
    const allowed = [...config.public_suites, ...config.components[o.component].suites];
    if (subcommand === 'test' && !allowed.includes(o.suite))
      throw new Failure(
        'Suite does not belong to this component; use private integration for consumers',
        2,
      );
    const plan = resolve(prepared.destination, '.artifacts/plan.json');
    run(['node', cli, 'ci', 'plan', '--scope', `component:${o.component}`, '--output', plan], {
      cwd: prepared.destination,
    });
    const suites = subcommand === 'test' ? [o.suite] : allowed;
    for (const suite of suites) {
      const result = run(['node', cli, 'test', '--suite', suite, '--plan', plan], {
        cwd: prepared.destination,
        timeout: 3_600_000,
      });
      process.stdout.write(result.stdout);
    }
    return output({ ...prepared, status: 'success', suites });
  }
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
    return output(inspectRun(o.run, { repo: o.repository }));
  }
  if (command === 'ci' && subcommand === 'metrics')
    return output(inspectMetrics(Number(o.limit ?? 20)));
  if (command === 'ci' && subcommand === 'authorize-private') {
    const result = run(['node', 'tools/admin/qualify-private.mjs', ...process.argv.slice(4)], {
      timeout: 120_000,
    });
    process.stdout.write(result.stdout);
    return;
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
    const component = o.component === 'sdk' ? 'solana' : o.component;
    if (workspaceConfig().components[component]) {
      guardPrivateSources([component]);
      requireSources([component]);
    }
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
      sdk: { cwd: 'chain/sdk', command: ['npm', 'run', 'build'] },
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
