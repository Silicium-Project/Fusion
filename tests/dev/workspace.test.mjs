import test from 'node:test';
import assert from 'node:assert/strict';
import {
  mkdtempSync,
  mkdirSync,
  writeFileSync,
  readFileSync,
  existsSync,
  rmSync,
  symlinkSync,
} from 'node:fs';
import { resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { run, writeJson } from '../../tools/lib/process.mjs';
import {
  validateWorkspace,
  workspaceStatus,
  initializeWorkspace,
  pinComponent,
  trackedSources,
  guardPrivateSources,
} from '../../tools/lib/workspace.mjs';
import { prepareComponent } from '../../tools/lib/component.mjs';
import { scopeSelection, registry, route, combinePlans } from '../../tools/lib/planner.mjs';
import { workspaceConfig } from '../../tools/lib/workspace.mjs';

function fixture(t, materialized = false) {
  const base = mkdtempSync(resolve(tmpdir(), 'silicium-workspace-test-'));
  t.after(() => rmSync(base, { recursive: true, force: true }));
  const source = resolve(base, 'source'),
    directory = resolve(base, 'policy');
  const git = (cwd, ...args) => run(['git', '-C', cwd, ...args]).stdout.trim();
  for (const path of [source, directory]) {
    mkdirSync(path);
    git(path, 'init', '--quiet');
    git(path, 'config', 'user.name', 'Fixture');
    git(path, 'config', 'user.email', 'fixture@silicium.invalid');
  }
  const config = {
    $schema: 'https://silicium.network/contracts/workspace/registry/v1',
    schema_version: 1,
    name: 'Workbench',
    repository: 'Silicium-Project/Workbench',
    repository_id: 1304063299,
    owner: 'Silicium-Project',
    visibility: 'public',
    default_branch: 'main',
    legacy_repositories: ['Silicium-Project/Fusion'],
    mode: 'multi-repo',
    integration_repository: 'Silicium-Project/Integration',
    integration: {
      repository: 'Silicium-Project/Integration',
      owner: 'Silicium-Project',
      visibility: 'private',
      default_branch: 'main',
      role: 'private cross-repository qualification',
    },
    public_suites: ['docs'],
    components: {
      api: {
        repository: 'Silicium-Project/BackEnd',
        owner: 'Silicium-Project',
        path: 'apps/api',
        default_branch: 'main',
        visibility: 'private',
        suites: ['api'],
      },
    },
  };
  writeJson(resolve(source, '.silicium-component.json'), {
    id: 'api',
    repository: 'Silicium-Project/BackEnd',
    workspace_path: 'apps/api',
  });
  writeFileSync(resolve(source, 'source with spaces.go'), 'package fixture\n');
  git(source, 'add', '.');
  git(source, 'commit', '--quiet', '-m', 'fixture source');
  const sha = git(source, 'rev-parse', 'HEAD');
  const lock = {
    $schema: 'https://silicium.network/contracts/workspace/pins/v1',
    schema_version: 1,
    repository: config.repository,
    components: {
      api: { repository: config.components.api.repository, path: 'apps/api', commit: sha },
    },
  };
  writeJson(resolve(directory, 'tools/config/workspace.json'), config);
  writeJson(resolve(directory, 'components.lock.json'), lock);
  writeFileSync(
    resolve(directory, '.gitmodules'),
    '[submodule "api"]\n path = apps/api\n url = https://github.com/Silicium-Project/BackEnd.git\n',
  );
  git(directory, 'add', '.');
  git(directory, 'update-index', '--add', '--cacheinfo', '160000', sha, 'apps/api');
  git(directory, 'commit', '--quiet', '-m', 'fixture policy');
  if (!materialized) mkdirSync(resolve(directory, 'apps/api'), { recursive: true });
  if (materialized) {
    git(directory, 'clone', '--shared', '--quiet', source, 'apps/api');
    git(
      resolve(directory, 'apps/api'),
      'remote',
      'set-url',
      'origin',
      'https://github.com/Silicium-Project/BackEnd.git',
    );
  }
  return { base, source, directory, config, lock, git, sha, environment: {} };
}

test('workspace pins reject missing components, floating refs, traversal and nested roots', (t) => {
  const { config, lock } = fixture(t);
  assert.equal(validateWorkspace(config, lock), lock);
  for (const mutate of [
    (c, l) => {
      delete l.components.api;
    },
    (c, l) => {
      l.components.api.commit = 'main';
    },
    (c) => {
      c.components.api.path = '../outside';
    },
    (c) => {
      c.components.api.repository = 'attacker/BackEnd';
    },
    (c, l) => {
      c.components.nested = { ...c.components.api, path: 'apps/api/nested' };
      l.components.nested = { ...l.components.api, path: 'apps/api/nested' };
    },
    (c) => {
      c.components.api.owner = 'Other-Organization';
    },
    (c) => {
      c.components.api.default_branch = '../main';
    },
    (c) => {
      c.default_branch = '';
    },
    (c) => {
      delete c.$schema;
    },
    (c) => {
      c.repository_id = 0;
    },
    (c) => {
      c.components.api.suites = [];
    },
    (c) => {
      c.integration.repository = 'other/Integration';
    },
    (c) => {
      c.integration.default_branch = '';
    },
  ]) {
    const c = structuredClone(config),
      l = structuredClone(lock);
    mutate(c, l);
    assert.throws(() => validateWorkspace(c, l));
  }
});

test('public verification accepts absent private sources but materialized verification blocks', (t) => {
  const { directory } = fixture(t);
  const status = workspaceStatus({ directory });
  assert.equal(status.status, 'success');
  assert.equal(status.registry.workbench.default_branch, 'main');
  assert.equal(status.registry.integration.visibility, 'private');
  assert.equal(status.registry.components.api.default_branch, 'main');
  assert.equal(workspaceStatus({ directory, materialized: true }).status, 'blocked');
  const preview = initializeWorkspace({ directory });
  assert.equal(preview.status, 'planned');
  assert.equal(existsSync(resolve(directory, 'apps/api/.git')), false);
});

test('initialization and pinning preserve dirty checkouts and pin previews do not mutate', (t) => {
  const { directory, sha } = fixture(t, true);
  assert.equal(workspaceStatus({ directory, materialized: true }).status, 'success');
  const before = readFileSync(resolve(directory, 'components.lock.json'), 'utf8');
  assert.equal(
    pinComponent({ directory, component: 'api', revision: 'a'.repeat(40) }).previous,
    sha,
  );
  assert.equal(readFileSync(resolve(directory, 'components.lock.json'), 'utf8'), before);
  writeFileSync(resolve(directory, 'apps/api/local.go'), 'preserve me');
  assert.throws(() => initializeWorkspace({ directory, apply: true }), /Preserve/);
  assert.throws(
    () => pinComponent({ directory, component: 'api', revision: 'a'.repeat(40), apply: true }),
    /modified/,
  );
  assert.equal(readFileSync(resolve(directory, 'apps/api/local.go'), 'utf8'), 'preserve me');
});

test('gitlink, lock and module identity must agree', (t) => {
  const { directory } = fixture(t);
  writeFileSync(
    resolve(directory, '.gitmodules'),
    '[submodule "api"]\n path = apps/api\n url = https://github.com/attacker/repository.git\n',
  );
  assert.equal(workspaceStatus({ directory }).components[0].state, 'invalid_pin');
  assert.throws(() => initializeWorkspace({ directory, apply: true }), /Preserve/);
});

test('source inventory keeps private tracked files, spaces, and excludes private sources when absent', (t) => {
  const { directory } = fixture(t, true);
  assert.ok(trackedSources({ directory }).includes('apps/api/source with spaces.go'));
  rmSync(resolve(directory, 'apps/api'), { recursive: true });
  assert.ok(!trackedSources({ directory }).includes('apps/api/source with spaces.go'));
});

test('private sources cannot be executed by public Workbench or an unrelated repository', () => {
  for (const repo of ['Silicium-Project/Workbench', 'attacker/repository'])
    assert.throws(
      () =>
        guardPrivateSources(['api'], {
          GITHUB_ACTIONS: 'true',
          GITHUB_REPOSITORY: repo,
          SILICIUM_SOURCE_VISIBILITY: 'private',
        }),
      /private repository/,
    );
  assert.throws(
    () =>
      guardPrivateSources(['api'], {
        GITHUB_ACTIONS: 'true',
        GITHUB_REPOSITORY: 'Silicium-Project/BackEnd',
      }),
    /private repository/,
  );
  assert.doesNotThrow(() =>
    guardPrivateSources(['api'], {
      GITHUB_ACTIONS: 'true',
      GITHUB_REPOSITORY: 'Silicium-Project/Integration',
      SILICIUM_SOURCE_VISIBILITY: 'private',
    }),
  );
});

test('component preparation is deterministic and preserves both original repositories', (t) => {
  const f = fixture(t);
  const head = f.git(f.directory, 'rev-parse', 'HEAD');
  const preview = prepareComponent({ ...f, component: 'api', expectedRevision: f.sha });
  assert.equal(preview.status, 'planned');
  const a = prepareComponent({
    ...f,
    component: 'api',
    apply: true,
    destination: resolve(f.base, 'composition-a'),
  });
  const b = prepareComponent({
    ...f,
    component: 'api',
    apply: true,
    destination: resolve(f.base, 'composition-b'),
  });
  assert.equal(a.composition_sha, b.composition_sha);
  assert.equal(a.source_sha, f.sha);
  assert.equal(workspaceStatus({ directory: a.destination, materialized: true }).status, 'success');
  assert.equal(f.git(f.directory, 'rev-parse', 'HEAD'), head);
  assert.equal(f.git(f.source, 'status', '--porcelain'), '');
  assert.throws(
    () => prepareComponent({ ...f, component: 'api', apply: true, destination: a.destination }),
    /must not exist/,
  );
  assert.throws(
    () => prepareComponent({ ...f, component: 'api', expectedRevision: 'f'.repeat(40) }),
    /requested source commit/,
  );
});

test('source preparation rejects public execution and uncommitted source changes', (t) => {
  const f = fixture(t);
  assert.throws(
    () =>
      prepareComponent({
        ...f,
        component: 'api',
        environment: { GITHUB_ACTIONS: 'true', GITHUB_REPOSITORY: 'Silicium-Project/Workbench' },
      }),
    /own repository/,
  );
  writeFileSync(resolve(f.source, 'local.go'), 'uncommitted');
  assert.throws(() => prepareComponent({ ...f, component: 'api', apply: true }), /local changes/);
});

test('a component symlink cannot escape the workspace', (t) => {
  if (process.platform === 'win32')
    return t.skip('symlink privilege is not available on standard Windows runners');
  const f = fixture(t);
  mkdirSync(resolve(f.directory, 'apps'), { recursive: true });
  rmSync(resolve(f.directory, 'apps/api'), { recursive: true });
  symlinkSync(f.source, resolve(f.directory, 'apps/api'), 'dir');
  assert.throws(() => workspaceStatus({ directory: f.directory }), /escapes/);
});

test('public CI has no application lanes; integration retains every application obligation', () => {
  const config = registry(),
    workspace = workspaceConfig(),
    selected = route(['tools/dev.mjs']);
  const publicPlan = scopeSelection(selected, 'public', config, workspace);
  assert.deepEqual(publicPlan.suites, [...workspace.public_suites].sort());
  assert.ok(
    scopeSelection(selected, 'integration', config, workspace).suites.includes('workspace-sources'),
  );
  for (const component of Object.keys(workspace.components))
    for (const suite of workspace.components[component].suites)
      assert.ok(scopeSelection(selected, 'integration', config, workspace).suites.includes(suite));
  const legacy = scopeSelection(
    selected,
    'public',
    { ...config, workspace_mode: undefined },
    workspace,
  );
  assert.equal(legacy.scope, 'legacy');
  assert.throws(
    () =>
      combinePlans({ ...publicPlan, head_sha: 'e'.repeat(40) }, { ...legacy, requirements: {} }),
    /administrator SHA/,
  );
  const migrationPlan = { ...publicPlan, head_sha: 'e'.repeat(40) };
  const previousPolicy = { ...legacy, requirements: {} };
  const trustedMainPush = {
    GITHUB_EVENT_NAME: 'push',
    GITHUB_REF: 'refs/heads/main',
    GITHUB_REPOSITORY: 'Silicium-Project/Workbench',
    SILICIUM_TRUSTED_MAIN_PUSH: 'true',
  };
  assert.deepEqual(
    combinePlans(migrationPlan, previousPolicy, trustedMainPush).suites,
    publicPlan.suites,
  );
  assert.throws(
    () =>
      combinePlans(migrationPlan, previousPolicy, {
        ...trustedMainPush,
        GITHUB_EVENT_NAME: 'pull_request',
      }),
    /administrator SHA/,
  );
});
