import { copyFileSync, existsSync, lstatSync, mkdirSync, readdirSync, realpathSync } from 'node:fs';
import { dirname, isAbsolute, relative, resolve, sep } from 'node:path';
import { Failure } from './process.mjs';

export const privateDeliveryStagePaths = Object.freeze({
  api: '.artifacts/build/api',
  web: 'apps/web/.output',
  network: '.artifacts/build/network',
  node_ui: 'apps/node/dist',
});

function copyRegularTree(source, destination) {
  const stat = lstatSync(source);
  if (stat.isSymbolicLink()) throw new Failure('Private delivery inputs cannot contain symlinks');
  if (stat.isFile()) {
    copyFileSync(source, destination);
    return;
  }
  if (!stat.isDirectory()) throw new Failure('Private delivery contains an unsupported file type');
  mkdirSync(destination);
  for (const name of readdirSync(source))
    copyRegularTree(resolve(source, name), resolve(destination, name));
}

function assertContainedParent(workspace, destination) {
  const root = realpathSync(workspace);
  const parent = realpathSync(dirname(destination));
  const rel = relative(root, parent);
  if (isAbsolute(rel) || rel === '..' || rel.startsWith(`..${sep}`))
    throw new Failure('Private delivery staging path escapes the Workbench checkout');
}

function assertWithin(boundary, candidate, message) {
  const rel = relative(boundary, candidate);
  if (isAbsolute(rel) || rel === '..' || rel.startsWith(`..${sep}`)) throw new Failure(message);
}

function assertNoSymlinkAncestors(workspace, destination) {
  const root = realpathSync(workspace);
  let current = dirname(destination);
  while (current !== root) {
    const rel = relative(root, current);
    if (isAbsolute(rel) || rel === '..' || rel.startsWith(`..${sep}`))
      throw new Failure('Private delivery staging path escapes the Workbench checkout');
    if (existsSync(current) && lstatSync(current).isSymbolicLink())
      throw new Failure('Private delivery staging refuses symlinked workspace directories');
    current = dirname(current);
  }
}

export function stagePrivateDelivery({ artifactRoot, workspace, artifacts }) {
  const workspaceRoot = realpathSync(workspace);
  const artifactBoundary = realpathSync(artifactRoot);
  assertWithin(
    workspaceRoot,
    artifactBoundary,
    'Private delivery artifact root escapes the Workbench checkout',
  );
  const suites = Object.keys(privateDeliveryStagePaths);
  const records = new Map(
    (Array.isArray(artifacts) ? artifacts : []).map((artifact) => [artifact?.suite, artifact]),
  );
  if (
    !Array.isArray(artifacts) ||
    artifacts.length !== suites.length ||
    new Set(artifacts.map((artifact) => artifact?.suite)).size !== suites.length ||
    suites.some((suite) => {
      const artifact = records.get(suite);
      return (
        !artifact ||
        !Number.isSafeInteger(artifact.id) ||
        artifact.id < 1 ||
        !/^sha256:[a-f0-9]{64}$/.test(artifact.digest ?? '') ||
        !Number.isSafeInteger(artifact.size_bytes) ||
        artifact.size_bytes < 1
      );
    })
  )
    throw new Failure('Private delivery staging requires exactly one verified artifact per suite');

  const planned = suites.map((suite) => {
    const target = privateDeliveryStagePaths[suite];
    const source = resolve(artifactRoot, suite === 'node_ui' ? 'node-ui' : suite);
    const destination = resolve(workspace, target);
    if (!existsSync(source) || !lstatSync(source).isDirectory())
      throw new Failure(`The verified ${suite} source artifact is missing or invalid`);
    assertWithin(
      artifactBoundary,
      realpathSync(source),
      `The verified ${suite} source artifact escapes its private artifact root`,
    );
    if (existsSync(destination))
      throw new Failure(`Refusing to overwrite an existing workspace path for ${suite}`);
    assertNoSymlinkAncestors(workspace, destination);
    mkdirSync(dirname(destination), { recursive: true });
    assertContainedParent(workspace, destination);
    return { suite, source, destination, target };
  });

  const rows = [];
  for (const item of planned) {
    copyRegularTree(item.source, item.destination);
    rows.push({ suite: item.suite, path: item.target });
  }
  return rows;
}
