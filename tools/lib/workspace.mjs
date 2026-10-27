/** Explicit component pins; public checks never fetch private source code. */
import { existsSync, realpathSync, readdirSync } from 'node:fs';
import { resolve, relative, isAbsolute } from 'node:path';
import { root, readJson, writeJson, run, Failure } from './process.mjs';

export const workspaceConfig = (directory = root) =>
  readJson(resolve(directory, 'tools/config/workspace.json'));
export const workspaceLock = (directory = root) =>
  readJson(resolve(directory, 'components.lock.json'));

export function validateWorkspace(config, lock) {
  if (
    config.$schema !== 'https://silicium.network/contracts/workspace/registry/v1' ||
    lock.$schema !== 'https://silicium.network/contracts/workspace/pins/v1' ||
    config.schema_version !== 1 ||
    lock.schema_version !== 1 ||
    typeof config.name !== 'string' ||
    !config.name ||
    lock.repository !== config.repository ||
    !Number.isSafeInteger(config.repository_id) ||
    config.repository_id < 1 ||
    config.owner !== config.repository?.split('/')[0] ||
    config.visibility !== 'public' ||
    config.mode !== 'multi-repo' ||
    !/^[A-Za-z0-9._-]+$/.test(config.default_branch ?? '') ||
    !Array.isArray(config.legacy_repositories) ||
    config.legacy_repositories.some(
      (repository) => !/^Silicium-Project\/[A-Za-z0-9._-]+$/.test(repository),
    ) ||
    !Array.isArray(config.public_suites) ||
    !config.public_suites.length ||
    config.public_suites.some((suite) => typeof suite !== 'string' || !suite) ||
    config.integration?.repository !== config.integration_repository ||
    !/^Silicium-Project\/[A-Za-z0-9._-]+$/.test(config.integration_repository ?? '') ||
    config.integration?.owner !== config.integration?.repository?.split('/')[0] ||
    config.integration?.visibility !== 'private' ||
    typeof config.integration?.role !== 'string' ||
    !config.integration.role ||
    !/^[A-Za-z0-9._-]+$/.test(config.integration?.default_branch ?? '')
  )
    throw new Failure('Unsupported workspace identity or lock schema', 2);
  const paths = new Set();
  const ids = Object.keys(config.components);
  if (!ids.length || Object.keys(lock.components).sort().join() !== ids.sort().join())
    throw new Failure('Component lock is incomplete or contains undeclared components', 2);
  for (const [id, entry] of Object.entries(config.components)) {
    const pin = lock.components[id];
    if (
      !/^[a-z][a-z0-9-]*$/.test(id) ||
      !/^Silicium-Project\/[A-Za-z0-9._-]+$/.test(entry.repository) ||
      entry.owner !== entry.repository.split('/')[0] ||
      !/^[A-Za-z0-9._-]+$/.test(entry.default_branch ?? '') ||
      !/^[a-zA-Z0-9_-]+(?:\/[a-zA-Z0-9_-]+)*$/.test(entry.path) ||
      paths.has(entry.path) ||
      entry.visibility !== 'private' ||
      !Array.isArray(entry.suites) ||
      !entry.suites.length ||
      entry.suites.some((suite) => typeof suite !== 'string' || !suite) ||
      !/^[a-f0-9]{40}$/.test(pin.commit ?? '') ||
      pin.repository !== entry.repository ||
      pin.path !== entry.path
    )
      throw new Failure(`Invalid component identity or immutable pin: ${id}`, 2);
    for (const path of paths)
      if (entry.path.startsWith(path + '/') || path.startsWith(entry.path + '/'))
        throw new Failure('Nested component roots are not supported', 2);
    paths.add(entry.path);
  }
  return lock;
}

const gitAt = (directory, ...args) => run(['git', '-C', directory, ...args]).stdout.trim();
const urlFor = (component) => `https://github.com/${component.repository}.git`;

export function workspaceStatus({ directory = root, materialized = false } = {}) {
  const config = workspaceConfig(directory),
    lock = validateWorkspace(config, workspaceLock(directory));
  const entries = [];
  for (const [id, component] of Object.entries(config.components)) {
    const pin = lock.components[id],
      path = resolve(directory, component.path);
    if (existsSync(path)) {
      const location = relative(realpathSync(directory), realpathSync(path));
      if (
        !location ||
        isAbsolute(location) ||
        location === '..' ||
        location.startsWith('../') ||
        location.startsWith('..\\')
      )
        throw new Failure(`Component escapes the workspace: ${id}`, 3);
    }
    const row = gitAt(directory, 'ls-tree', 'HEAD', '--', component.path).split(/\s+/);
    const mode = row[0],
      indexed = row[2];
    const moduleUrl = run(
      ['git', '-C', directory, 'config', '-f', '.gitmodules', '--get', `submodule.${id}.url`],
      { allowFailure: true },
    ).stdout.trim();
    const modulePath = run(
      ['git', '-C', directory, 'config', '-f', '.gitmodules', '--get', `submodule.${id}.path`],
      { allowFailure: true },
    ).stdout.trim();
    let state = 'absent',
      actual = null;
    if (
      mode !== '160000' ||
      indexed !== pin.commit ||
      moduleUrl !== urlFor(component) ||
      modulePath !== component.path
    )
      state = 'invalid_pin';
    else if (existsSync(resolve(path, '.git'))) {
      const localRoot = gitAt(path, 'rev-parse', '--show-toplevel');
      if (realpathSync(localRoot) !== realpathSync(path))
        throw new Failure(`Unexpected component root: ${id}`, 3);
      actual = gitAt(path, 'rev-parse', 'HEAD');
      const dirty = gitAt(path, 'status', '--porcelain', '--untracked-files=normal');
      state = dirty ? 'modified' : actual !== pin.commit ? 'different_revision' : 'ready';
    } else if (existsSync(path) && readdirSync(path).length) state = 'occupied';
    entries.push({
      id,
      repository: component.repository,
      owner: component.owner,
      path: component.path,
      default_branch: component.default_branch,
      expected: pin.commit,
      actual,
      state,
    });
  }
  const invalid = entries.filter((entry) =>
    materialized ? entry.state !== 'ready' : !['ready', 'absent'].includes(entry.state),
  );
  return {
    schema_version: 1,
    operation: 'workspace.verify',
    repository: config.repository,
    registry: {
      workbench: {
        repository: config.repository,
        repository_id: config.repository_id,
        owner: config.owner,
        visibility: config.visibility,
        default_branch: config.default_branch,
      },
      integration: { ...config.integration },
      components: Object.fromEntries(
        Object.entries(config.components).map(([id, component]) => [id, { ...component }]),
      ),
    },
    status: invalid.length ? 'blocked' : 'success',
    materialized,
    components: entries,
  };
}

export function requireSources(ids, directory = root) {
  const status = workspaceStatus({ directory });
  for (const id of ids) {
    const entry = status.components.find((component) => component.id === id);
    if (!entry || entry.state !== 'ready')
      throw new Failure(
        `Component ${id} is ${entry?.state ?? 'undeclared'}; run dev workspace init --component ${id} --apply, preserving local work`,
        2,
      );
  }
  return status;
}

export function sourceIdentity(directory = root) {
  return existsSync(resolve(directory, 'components.lock.json'))
    ? workspaceLock(directory).components
    : null;
}

export function guardPrivateSources(ids, environment = process.env, directory = root) {
  if (!ids.length || environment.GITHUB_ACTIONS !== 'true') return;
  const config = workspaceConfig(directory);
  const allowed = [
    config.integration_repository,
    ...ids.map((id) => config.components[id]?.repository),
  ];
  if (
    !allowed.includes(environment.GITHUB_REPOSITORY) ||
    environment.SILICIUM_SOURCE_VISIBILITY !== 'private'
  )
    throw new Failure(
      'Private application qualification requires an authorized private repository; Workbench CI cannot execute these sources',
      3,
    );
}

export function initializeWorkspace({ component, apply = false, directory = root } = {}) {
  const config = workspaceConfig(directory),
    lock = validateWorkspace(config, workspaceLock(directory));
  const selected = component ? [component] : Object.keys(config.components);
  for (const id of selected)
    if (!config.components[id]) throw new Failure(`Unknown component: ${id}`, 2);
  const before = workspaceStatus({ directory });
  for (const id of selected) {
    const entry = before.components.find((row) => row.id === id);
    if (!['absent', 'ready'].includes(entry.state))
      throw new Failure(
        `Preserve ${id}: ${entry.state}; initialization never replaces an existing checkout`,
        3,
      );
  }
  if (apply)
    for (const id of selected) {
      const path = config.components[id].path;
      gitAt(directory, 'submodule', 'update', '--init', '--checkout', '--', path);
      if (gitAt(resolve(directory, path), 'rev-parse', 'HEAD') !== lock.components[id].commit)
        throw new Failure(`Checkout did not produce the pinned revision: ${id}`, 3);
    }
  return {
    schema_version: 1,
    operation: 'workspace.init',
    status: apply ? 'applied' : 'planned',
    components: selected,
    verification: apply ? workspaceStatus({ directory }) : before,
  };
}

export function pinComponent({ component, revision, apply = false, directory = root } = {}) {
  const config = workspaceConfig(directory),
    lock = validateWorkspace(config, workspaceLock(directory));
  const entry = config.components[component];
  if (!entry || !/^[a-f0-9]{40}$/.test(revision ?? ''))
    throw new Failure('Provide a declared component and a complete commit SHA', 2);
  requireSources([component], directory);
  const path = resolve(directory, entry.path);
  const previous = lock.components[component].commit;
  const remote = gitAt(path, 'remote', 'get-url', 'origin');
  if (![urlFor(entry), `git@github.com:${entry.repository}.git`].includes(remote))
    throw new Failure('Component origin does not match the declared repository', 3);
  if (apply) {
    gitAt(path, 'fetch', '--no-tags', 'origin', revision);
    gitAt(path, 'checkout', '--detach', revision);
    lock.components[component].commit = revision;
    writeJson(resolve(directory, 'components.lock.json'), lock);
    gitAt(directory, 'add', '--', entry.path, 'components.lock.json');
  }
  return {
    schema_version: 1,
    operation: 'workspace.pin',
    status: apply ? 'applied' : 'planned',
    component,
    previous,
    revision,
  };
}

export function trackedSources({ directory = root, untracked = false } = {}) {
  const args = ['ls-files', '-z', '-c', ...(untracked ? ['-o', '--exclude-standard'] : [])];
  const files = run(['git', '-C', directory, ...args])
    .stdout.split('\0')
    .filter(Boolean);
  if (existsSync(resolve(directory, 'components.lock.json'))) {
    for (const component of Object.values(workspaceConfig(directory).components)) {
      const path = resolve(directory, component.path);
      if (!existsSync(resolve(path, '.git'))) continue;
      for (const file of run(['git', '-C', path, ...args])
        .stdout.split('\0')
        .filter(Boolean)) {
        const full = resolve(path, file),
          rel = relative(directory, full);
        if (isAbsolute(rel) || rel.startsWith('../') || rel.startsWith('..\\'))
          throw new Failure('A component file escapes its workspace', 3);
        files.push(`${component.path}/${file}`);
      }
    }
  }
  return [...new Set(files)];
}
