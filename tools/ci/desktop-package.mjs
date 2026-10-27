/** Channel-specific installer; reuse the tested UI, compile each native target once. */
import { mkdirSync, readdirSync, cpSync, existsSync, chmodSync } from 'node:fs';
import { resolve, basename } from 'node:path';
import { run, root, readJson, writeJson, Failure } from '../lib/process.mjs';
import { packageVersions } from '../lib/manifest.mjs';
const channel = process.env.RELEASE_CHANNEL;
const version = process.env.RELEASE_VERSION;
if (!['dev', 'prod'].includes(channel)) throw new Failure('Explicit channel required');
const versions = packageVersions(version);
const app = resolve(root, 'apps/node');
const runtime = resolve(app, 'src-tauri/resources/runtime');
const networkArtifacts = resolve(root, '.artifacts/build/network');
mkdirSync(runtime, { recursive: true });
const suffix = process.platform === 'win32' ? '.exe' : '';
if (process.platform === 'win32')
  run(
    [
      'cargo',
      'build',
      '--release',
      '--locked',
      '--manifest-path',
      'network/Cargo.toml',
      '-p',
      'p2p_node',
      '-p',
      'compute_daemon',
      '-p',
      'silicium-raytracer',
    ],
    { timeout: 3_600_000 },
  );
else if (
  !['p2p_node', 'compute_daemon', 'silicium-raytracer'].every((name) =>
    existsSync(resolve(networkArtifacts, name)),
  )
)
  throw new Failure('Linux packaging must reuse the binaries from the qualified network artifact');

function networkBinary(name) {
  return process.platform === 'win32'
    ? resolve(root, 'network/target/release', `${name}${suffix}`)
    : resolve(networkArtifacts, name);
}

mkdirSync(resolve(runtime, 'Network/bin/raytracer'), { recursive: true });
for (const name of ['p2p_node', 'compute_daemon']) {
  const destination = resolve(runtime, `Network/bin/${name}${suffix}`);
  cpSync(networkBinary(name), destination);
  if (process.platform !== 'win32') chmodSync(destination, 0o755);
}
const raytracerDestination = resolve(runtime, `Network/bin/raytracer/silicium-raytracer${suffix}`);
cpSync(networkBinary('silicium-raytracer'), raytracerDestination);
if (process.platform !== 'win32') chmodSync(raytracerDestination, 0o755);
const config = {
  version,
  build: { beforeBuildCommand: '' },
  bundle: {
    ...(process.platform === 'win32'
      ? { windows: { nsis: { displayLanguageSelector: true } } }
      : {
          linux: {
            deb: { depends: ['curl', 'openssl', 'ca-certificates'] },
            rpm: { release: versions.rpm_release },
          },
        }),
  },
};
writeJson(resolve(app, 'src-tauri/ci.conf.json'), config);
const configs = channel === 'prod' ? ['--config', 'src-tauri/tauri.prod.conf.json'] : [];
run(['npm', 'ci'], { cwd: app });
// UI output was downloaded from the qualifying CI, never rebuilt in packaging.
if (process.platform === 'linux')
  run(['node', 'tools/ci/appimage-tools.mjs'], { timeout: 600_000 });
run(
  [
    'npm',
    'exec',
    '--',
    'tauri',
    'build',
    ...configs,
    '--config',
    'src-tauri/ci.conf.json',
    '--bundles',
    process.platform === 'win32' ? 'nsis' : 'deb,rpm,appimage',
  ],
  {
    cwd: app,
    env: {
      SILICIUM_RELEASE_CHANNEL: channel,
      SILICIUM_RELEASE_VERSION: version,
      SILICIUM_RELEASE_BUILD: process.env.SOURCE_SHA,
      APPIMAGE_EXTRACT_AND_RUN: '1',
      NO_STRIP: 'true',
    },
    timeout: 3_600_000,
  },
);
const out = resolve(root, '.artifacts/installers');
mkdirSync(out, { recursive: true });
for (const file of readdirSync(resolve(app, 'src-tauri/target/release/bundle'), {
  recursive: true,
}).filter((n) => /\.(deb|rpm|exe|AppImage)$/.test(n)))
  cpSync(resolve(app, 'src-tauri/target/release/bundle', file), resolve(out, basename(file)));
writeJson(resolve(out, `versions-${process.platform}.json`), versions);
