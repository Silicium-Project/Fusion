/** Qualify one private component with a recorded, deterministic Workbench composition. */
import { existsSync, realpathSync, mkdtempSync } from 'node:fs';
import { resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { root, run, readJson, writeJson, Failure } from './process.mjs';
import { workspaceConfig, workspaceLock, validateWorkspace } from './workspace.mjs';

export function prepareComponent({
  component,
  source,
  destination,
  expectedRevision,
  apply = false,
  directory = root,
  environment = process.env,
} = {}) {
  const config = workspaceConfig(directory),
    lock = validateWorkspace(config, workspaceLock(directory));
  const entry = config.components[component];
  if (!entry || !source)
    throw new Failure('Provide --component and --source for a declared component', 2);
  if (environment.GITHUB_ACTIONS === 'true' && environment.GITHUB_REPOSITORY !== entry.repository)
    throw new Failure(
      'A component must be qualified in its own repository; public Workbench never fetches private source',
      3,
    );
  const sourcePath = realpathSync(resolve(source));
  const at = (cwd, ...args) => run(['git', '-C', cwd, ...args]).stdout.trim();
  if (realpathSync(at(sourcePath, 'rev-parse', '--show-toplevel')) !== sourcePath)
    throw new Failure('Source must be the component repository root', 2);
  const metadata = readJson(resolve(sourcePath, '.silicium-component.json'));
  if (
    metadata.id !== component ||
    metadata.repository !== entry.repository ||
    metadata.workspace_path !== entry.path
  )
    throw new Failure('The source identity does not match the declared component', 3);
  const revision = at(sourcePath, 'rev-parse', 'HEAD');
  if (expectedRevision && revision !== expectedRevision)
    throw new Failure('Component checkout does not match the requested source commit', 3);
  if (at(sourcePath, 'status', '--porcelain', '--untracked-files=normal'))
    throw new Failure('Commit or preserve local changes before creating qualification evidence', 3);
  if (at(directory, 'status', '--porcelain', '--untracked-files=normal'))
    throw new Failure('Workbench policy must be a clean committed checkout', 3);
  const policy = at(directory, 'rev-parse', 'HEAD');
  const context = {
    schema_version: 1,
    component,
    repository: entry.repository,
    source_sha: revision,
    policy_repository: config.repository,
    policy_sha: policy,
  };
  if (!apply)
    return {
      ...context,
      operation: 'component.prepare',
      status: 'planned',
      destination: destination ? resolve(destination) : null,
    };
  const target = destination
    ? resolve(destination)
    : resolve(mkdtempSync(resolve(tmpdir(), 'silicium-component-')), 'workspace');
  if (existsSync(target))
    throw new Failure(
      'The qualification destination must not exist; existing files are preserved',
      2,
    );
  run(['git', 'clone', '--shared', '--no-hardlinks', '--no-checkout', '--', directory, target]);
  at(target, 'checkout', '--detach', policy);
  at(target, 'remote', 'remove', 'origin');
  const componentTarget = resolve(target, entry.path);
  run([
    'git',
    'clone',
    '--shared',
    '--no-hardlinks',
    '--no-checkout',
    '--',
    sourcePath,
    componentTarget,
  ]);
  at(componentTarget, 'checkout', '--detach', revision);
  at(componentTarget, 'remote', 'set-url', 'origin', `https://github.com/${entry.repository}.git`);
  lock.components[component].commit = revision;
  writeJson(resolve(target, 'components.lock.json'), lock);
  writeJson(resolve(target, '.component-qualification.json'), context);
  at(target, 'add', '--', 'components.lock.json', '.component-qualification.json');
  at(target, 'update-index', '--add', '--cacheinfo', '160000', revision, entry.path);
  const tree = at(target, 'write-tree');
  const synthetic = run(['git', '-C', target, 'commit-tree', tree, '-p', policy], {
    input: `Qualify ${component} ${revision} with policy ${policy}\n`,
    env: {
      GIT_AUTHOR_NAME: 'Silicium Qualification',
      GIT_AUTHOR_EMAIL: 'qualification@silicium.invalid',
      GIT_COMMITTER_NAME: 'Silicium Qualification',
      GIT_COMMITTER_EMAIL: 'qualification@silicium.invalid',
      GIT_AUTHOR_DATE: '2000-01-01T00:00:00Z',
      GIT_COMMITTER_DATE: '2000-01-01T00:00:00Z',
    },
  }).stdout.trim();
  at(target, 'update-ref', 'HEAD', synthetic, policy);
  if (at(target, 'status', '--porcelain', '--untracked-files=normal'))
    throw new Failure('Component preparation produced a dirty composition', 3);
  return {
    ...context,
    operation: 'component.prepare',
    status: 'applied',
    destination: target,
    composition_sha: synthetic,
  };
}
