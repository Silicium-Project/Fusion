/** Candidate assembly uses qualified main artifacts. No PR artifact enters publication. */
import { readdirSync, readFileSync, appendFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { root, run, readJson, writeJson, Failure } from '../lib/process.mjs';
import { verifiedRun, api, repository } from '../lib/github.mjs';
import { sha256, requireManifest, compareVersions } from '../lib/manifest.mjs';
import { qualifiedBuildArtifacts } from '../lib/release-artifacts.mjs';
const operation = process.argv[2];
const dir = resolve(root, '.artifacts/candidate');
mkdirSync(dir, { recursive: true });
if (operation === 'prepare') {
  const id = process.env.QUALIFICATION_RUN;
  const qualified = verifiedRun(id);
  const source = run(['git', 'rev-parse', 'HEAD']).stdout.trim();
  if (source !== qualified.head_sha) throw new Failure('Checkout does not match qualified source');
  const channel = process.env.RELEASE_CHANNEL ?? 'dev';
  const artifactRows = api(
    `repos/${repository}/actions/runs/${id}/artifacts?per_page=100`,
  ).artifacts;
  const artifacts = new Set(artifactRows.filter((x) => !x.expired).map((x) => x.name));
  const required = qualifiedBuildArtifacts(qualified.run_attempt);
  const changed = Object.keys(required).filter((c) => artifacts.has(required[c]));
  if (!changed.length) throw new Failure('No deliverable changed; this CI requires no release', 4);
  let previous = null;
  const releases = api(`repos/${repository}/releases?per_page=100`);
  const prior = releases.find(
    (r) =>
      !r.draft &&
      new RegExp(`^${channel}-[0-9]+\\.[0-9]+\\.[0-9]+(?:-dev\\.[0-9]+)?-[a-f0-9]{12}$`).test(
        r.tag_name,
      ),
  );
  if (prior) {
    const previousDir = resolve(dir, 'previous');
    mkdirSync(previousDir, { recursive: true });
    run([
      'gh',
      'release',
      'download',
      prior.tag_name,
      '--repo',
      repository,
      '--dir',
      previousDir,
      '--pattern',
      'manifest.json*',
    ]);
    // The trust anchor is installed during the reviewed signing-key migration.
    run([
      'gpgv',
      '--keyring',
      resolve(root, 'contracts/trust/release.gpg'),
      resolve(previousDir, 'manifest.json.asc'),
      resolve(previousDir, 'manifest.json'),
    ]);
    previous = requireManifest(readJson(resolve(previousDir, 'manifest.json')));
    if (previous.channel !== channel || previous.release_id !== prior.tag_name)
      throw new Failure('Previous signed candidate identity mismatch');
    if (
      run(['git', 'merge-base', '--is-ancestor', previous.source_sha, source], {
        allowFailure: true,
      }).status
    )
      throw new Failure('Publication would cross unrelated or older source history');
    writeJson(resolve(dir, 'previous.json'), previous);
    if (!changed.includes('node')) {
      run([
        'gh',
        'release',
        'download',
        prior.tag_name,
        '--repo',
        repository,
        '--dir',
        resolve(root, '.artifacts/publish'),
        '--pattern',
        'packages.tar.gz',
      ]);
      const asset = previous.assets.find((a) => a.name === 'packages.tar.gz');
      if (
        !asset ||
        sha256(readFileSync(resolve(root, '.artifacts/publish/packages.tar.gz'))) !== asset.sha256
      )
        throw new Failure('Previous package snapshot digest mismatch');
    }
  }
  if (!previous && changed.length < 4)
    throw new Failure('First integration candidate requires every component output');
  writeJson(resolve(dir, 'inputs.json'), {
    changed,
    artifacts: Object.fromEntries(changed.map((c) => [c, required[c]])),
    previous,
  });
  appendFileSync(process.env.GITHUB_OUTPUT, `node_changed=${changed.includes('node')}\n`);

  const version =
    channel === 'dev'
      ? `${readJson(resolve(root, 'tools/config/delivery.json')).base_version}-dev.${process.env.GITHUB_RUN_NUMBER}`
      : process.env.RELEASE_VERSION;
  if (channel === 'prod' && !/^\d+\.\d+\.\d+$/.test(version ?? ''))
    throw new Failure('Production version must be explicit');
  if (previous && compareVersions(version, previous.version) <= 0)
    throw new Failure('Candidate version must be newer than the preceding signed release');
  const release_id = `${channel}-${version}-${source.slice(0, 12)}`;
  const existing = run(
    ['gh', 'release', 'view', release_id, '--repo', repository, '--json', 'tagName'],
    { allowFailure: true },
  );
  if (!existing.status)
    throw new Failure(
      'Candidate already published; promote the existing identity rather than replacing assets',
    );
  writeJson(resolve(dir, 'identity.json'), {
    schema_version: 1,
    source_sha: source,
    channel,
    version,
    release_id,
    qualification: {
      source_sha: source,
      status: 'success',
      run_id: Number(id),
      run_attempt: Number(qualified.run_attempt),
    },
  });
  appendFileSync(
    process.env.GITHUB_OUTPUT,
    `source_sha=${source}\nrelease_id=${release_id}\nversion=${version}\nchannel=${channel}\nqualification_attempt=${qualified.run_attempt}\n`,
  );
} else if (operation === 'images') {
  const identity = readJson(resolve(dir, 'identity.json'));
  const inputs = readJson(resolve(dir, 'inputs.json'));
  const components = { ...(inputs.previous?.components ?? {}) };
  for (const component of ['api', 'web', 'network'].filter((c) => inputs.changed.includes(c))) {
    const pkg = api(`orgs/Silicium-Project/packages/container/${component}`);
    if (pkg.visibility !== 'public')
      throw new Failure(
        'GHCR package must be public before publication; private storage is forbidden by the budget policy',
      );
    const tag = `ghcr.io/silicium-project/${component}:${identity.release_id}`;
    const existing = run(['docker', 'buildx', 'imagetools', 'inspect', tag], {
      allowFailure: true,
    });
    if (!existing.status)
      throw new Failure(
        'Image identity already exists; start a fresh release run instead of overwriting it',
      );
    const digestFile = resolve(dir, `${component}.digest`);
    const dockerfile = `infra/images/${component}-runtime.Dockerfile`;
    run(
      [
        'docker',
        'buildx',
        'build',
        '--platform',
        'linux/amd64',
        '--provenance=mode=max',
        '--sbom=true',
        '--push',
        '--metadata-file',
        digestFile,
        '--label',
        `org.opencontainers.image.revision=${identity.source_sha}`,
        '--label',
        `org.opencontainers.image.version=${identity.version}`,
        '-f',
        dockerfile,
        '-t',
        tag,
        '.',
      ],
      { timeout: 3_600_000 },
    );
    const digest = readJson(digestFile)['containerimage.digest'];
    if (!/^sha256:[a-f0-9]{64}$/.test(digest ?? ''))
      throw new Failure('Missing immutable image digest');
    components[component] = {
      source_sha: identity.source_sha,
      image: `ghcr.io/silicium-project/${component}@${digest}`,
      platform: 'linux-x86_64',
      qualification_run: identity.qualification.run_id,
    };
  }
  writeJson(resolve(dir, 'components.json'), components);
} else if (operation === 'manifest') {
  const identity = readJson(resolve(dir, 'identity.json'));
  const assetsDir = resolve(root, '.artifacts/publish');
  const assets = readdirSync(assetsDir)
    .filter((n) => n !== 'manifest.json' && n !== 'manifest.json.asc')
    .map((name) => {
      const bytes = readFileSync(resolve(assetsDir, name));
      return { name, size: bytes.length, sha256: sha256(bytes) };
    });
  const nodeInput = readJson(resolve(dir, 'inputs.json'));
  const components = readJson(resolve(dir, 'components.json'));
  if (nodeInput.changed.includes('node'))
    components.node = {
      source_sha: identity.source_sha,
      version: identity.version,
      channel: identity.channel,
      platforms: ['linux-x86_64', 'windows-x86_64'],
      qualification_run: identity.qualification.run_id,
    };
  const m = requireManifest({
    ...identity,
    created_at: new Date().toISOString(),
    compatibility: { data_schema: 1, rollback: 'application-only', program_upgrade: false },
    components,
    assets,
  });
  writeJson(resolve(assetsDir, 'manifest.json'), m);
  appendFileSync(
    process.env.GITHUB_OUTPUT,
    `manifest_digest=${sha256(readFileSync(resolve(assetsDir, 'manifest.json')))}\n`,
  );
} else if (operation === 'publish') {
  const m = requireManifest(readJson(resolve(root, '.artifacts/publish/manifest.json')));
  const files = readdirSync(resolve(root, '.artifacts/publish')).map((n) =>
    resolve(root, '.artifacts/publish', n),
  );
  run(
    [
      'gh',
      'release',
      'create',
      m.release_id,
      '--repo',
      repository,
      '--target',
      m.source_sha,
      '--title',
      m.release_id,
      '--notes',
      `Candidat qualifié : ${m.source_sha}\nCI : https://github.com/${repository}/actions/runs/${m.qualification.run_id}`,
      ...(m.channel === 'dev' ? ['--prerelease'] : []),
      ...files,
    ],
    { timeout: 600_000 },
  );
  // This event is explicit: GITHUB_TOKEN release events do not recursively trigger Actions.
  api(`repos/${repository}/actions/workflows/deploy.yml/dispatches`, {
    method: 'POST',
    body: { ref: 'main', inputs: { release_id: m.release_id, environment: m.channel } },
  });
} else throw new Failure('Expected prepare|images|manifest|publish', 2);
