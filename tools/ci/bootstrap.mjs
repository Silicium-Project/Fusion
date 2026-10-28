/** Explicit GitHub runner bootstrap. Never installs operating-system packages on a user's PC. */
import { resolve } from 'node:path';
import { existsSync, mkdirSync, appendFileSync } from 'node:fs';
import { run, root, readJson, Failure, writeJson, git } from '../lib/process.mjs';
import { installSolana } from './solana-tools.mjs';
import { installAnchor } from './anchor-tools.mjs';
const suite = process.argv[2];
if (process.env.GITHUB_ACTIONS !== 'true')
  throw new Failure('Runner bootstrap is CI-only; use dev doctor locally', 2);
const tools = readJson(resolve(root, 'tools/config/toolchains.json'));
const output = (args, options = {}) => {
  const r = run(args, { timeout: 2_400_000, ...options });
  process.stdout.write(r.stdout);
  process.stderr.write(r.stderr);
  return r;
};
try {
  const rust = [
    'network',
    'network-wasm',
    'network-integration',
    'node-native',
    'node-windows',
    'solana',
  ].includes(suite);
  if (rust) {
    output([
      'rustup',
      'toolchain',
      'install',
      suite === 'solana' ? tools.rust_solana : tools.rust,
      '--profile',
      'minimal',
      '--component',
      'clippy,rustfmt',
    ]);
  }
  if (process.platform === 'linux' && ['node-native', 'solana'].includes(suite)) {
    output(['sudo', 'apt-get', 'update']);
    const packages =
      suite === 'node-native'
        ? [
            'libgtk-3-dev',
            'libwebkit2gtk-4.1-dev',
            'libayatana-appindicator3-dev',
            'librsvg2-dev',
            'patchelf',
            'pkg-config',
            'file',
            'rpm',
            'libfuse2',
          ]
        : ['pkg-config', 'libssl-dev', 'libudev-dev', 'clang', 'cmake'];
    output(['sudo', 'apt-get', 'install', '-y', '--no-install-recommends', ...packages]);
  }
  if (['network-integration', 'network-contract', 'infrastructure'].includes(suite))
    output([
      'python3',
      '-m',
      'pip',
      'install',
      '--require-hashes',
      '-r',
      'network/requirements-dev.txt',
    ]);
  if (suite === 'solana') {
    output(['npm', 'install', '--global', `yarn@${tools.yarn}`]);
    const home = resolve(process.env.RUNNER_TOOL_CACHE, 'silicium-solana', tools.solana);
    mkdirSync(home, { recursive: true });
    const bin = await installSolana(home, tools.solana);
    const anchorRoot = resolve(process.env.RUNNER_TOOL_CACHE, 'silicium-anchor', tools.anchor);
    const anchorBin = await installAnchor(anchorRoot, tools.anchor);
    appendFileSync(process.env.GITHUB_PATH, `${bin}\n${anchorBin}\n`);
  }
  console.log(`Runner prepared for ${suite}`);
} catch (error) {
  const planPath = resolve(root, '.artifacts/plan.json');
  const plan = existsSync(planPath) ? readJson(planPath) : null;
  writeJson(resolve(root, `.artifacts/reports/${suite}.json`), {
    schema_version: 1,
    suite,
    source_sha: git('rev-parse', 'HEAD'),
    policy_digest: plan?.policy_digest,
    dirty: false,
    status: 'failure',
    failure_kind: 'infrastructure',
    stage: 'bootstrap',
    steps: [],
    error: 'Prerequisite installation failed; inspect the Prepare runner step.',
  });
  throw error;
}
