/** Execute the website's exact snippets in disposable distro containers. Only transport URLs are rebased. */
import { resolve, join } from 'node:path';
import { mkdirSync, cpSync, existsSync, readFileSync, writeFileSync } from 'node:fs';
import { root, run, readJson, writeJson, Failure } from '../lib/process.mjs';
import { sha256, packageVersions } from '../lib/manifest.mjs';
import { repositoryCommands } from '../../contracts/install/repositories.mjs';
import { repository } from '../lib/github.mjs';
if (process.env.GITHUB_ACTIONS !== 'true' || !/^\d+$/.test(process.env.GITHUB_RUN_ID ?? ''))
  throw new Failure('Installation qualification needs a disposable GitHub runner', 2);
const identity = readJson(resolve(root, '.artifacts/candidate/identity.json'));
const channel = identity.channel;
if (!['dev', 'prod'].includes(channel)) throw new Failure('Invalid installation channel', 2);
const current = resolve(root, '.artifacts/snapshot'),
  fixture = resolve(root, '.artifacts/installation-http'),
  checks = resolve(root, '.artifacts/installation-scripts');
const network = `silicium-install-${process.env.GITHUB_RUN_ID}`,
  http = `${network}-http`,
  base = `http://${http}/downloads/snapshots`;
mkdirSync(fixture, { recursive: true });
mkdirSync(checks, { recursive: true });
function fixtureSnapshot(directory) {
  const snapshot = readJson(join(directory, 'snapshot.json'));
  if (!/^(dev|prod)-[0-9A-Za-z.-]+$/.test(snapshot.release_id ?? ''))
    throw new Failure('Invalid package snapshot identity');
  for (const [name, digest] of Object.entries(snapshot.files)) {
    if (
      name.startsWith('/') ||
      name.split('/').includes('..') ||
      sha256(readFileSync(join(directory, name))) !== digest
    )
      throw new Failure('Package fixture integrity mismatch');
  }
  const output = resolve(fixture, 'downloads/snapshots', snapshot.release_id);
  cpSync(directory, output, { recursive: true, errorOnExist: true, force: false });
  const apt = join(output, 'apt/silicium.sources'),
    rpm = join(output, 'rpm/silicium-node.repo');
  // These two unsigned transport pointers are the only changes to the test copy.
  writeFileSync(
    apt,
    readFileSync(apt, 'utf8').replace(/^URIs:.*$/m, `URIs: ${base}/${snapshot.release_id}/apt`),
  );
  writeFileSync(
    rpm,
    readFileSync(rpm, 'utf8')
      .replace(/^baseurl=.*$/m, `baseurl=${base}/${snapshot.release_id}/rpm`)
      .replace(
        /^gpgkey=.*$/m,
        `gpgkey=${base}/${snapshot.release_id}/rpm/silicium-rpm-signing.asc`,
      ),
  );
  return snapshot.release_id;
}
const latest = fixtureSnapshot(current);
let previous = null,
  previousVersion = null;
const previousPath = resolve(root, '.artifacts/candidate/previous.json');
if (existsSync(previousPath)) {
  const old = readJson(previousPath);
  previousVersion = old.components.node.version;
  if (previousVersion && previousVersion !== identity.version) {
    const asset = old.assets.find((asset) => asset.name === 'packages.tar.gz');
    const directory = resolve(root, '.artifacts/previous-installation');
    mkdirSync(directory, { recursive: true });
    run([
      'gh',
      'release',
      'download',
      old.release_id,
      '--repo',
      repository,
      '--dir',
      directory,
      '--pattern',
      'packages.tar.gz',
    ]);
    if (!asset || sha256(readFileSync(join(directory, 'packages.tar.gz'))) !== asset.sha256)
      throw new Failure('Previous package snapshot digest mismatch');
    run([
      'python3',
      '-c',
      "import importlib.util,sys,pathlib; s=importlib.util.spec_from_file_location('delivery',sys.argv[1]); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); m.extract(pathlib.Path(sys.argv[2]),pathlib.Path(sys.argv[3]))",
      resolve(root, 'infra/delivery/apply.py'),
      join(directory, 'packages.tar.gz'),
      join(directory, 'unpacked'),
    ]);
    previous = fixtureSnapshot(join(directory, 'unpacked/downloads'));
  }
}
for (const [label, rid] of [
  ['current', latest],
  ['previous', previous],
].filter(([, rid]) => rid)) {
  for (const manager of ['apt', 'dnf']) {
    const scripts = repositoryCommands(manager, channel, {
      baseURL: `${base}/${rid}`,
      testTransport: true,
    });
    for (const [name, text] of Object.entries(scripts))
      writeFileSync(
        join(checks, `${label}-${manager}-${name}.sh`),
        `#!/bin/bash\nset -euo pipefail\n${text}\n`,
      );
  }
}
const images = [
  {
    manager: 'apt',
    image: 'debian:12@sha256:854dd8ab51d62866dbd8f5431d15ce77b12983a2a4a1e1fe43a2395dc7ef9f61',
  },
  {
    manager: 'apt',
    image: 'ubuntu:24.04@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac',
  },
  {
    manager: 'dnf',
    image: 'fedora:44@sha256:43b29f65a41eb9c35e1cd5323e3bdf3b655c2357a9f4f1ff2f9c2798e5045d80',
  },
];
let count = 0;
run(['docker', 'network', 'create', network]);
try {
  run([
    'docker',
    'run',
    '-d',
    '--rm',
    '--name',
    http,
    '--network',
    network,
    '--mount',
    `type=bind,src=${fixture},dst=/usr/share/nginx/html,readonly`,
    'nginx:1.27-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10',
  ]);
  for (const { manager, image } of images)
    for (const mode of previous ? ['fresh', 'upgrade'] : ['fresh']) {
      const isApt = manager === 'apt';
      const setup = isApt
        ? `apt-get update -qq
apt-get install -y --no-install-recommends sudo curl gnupg ca-certificates
printf 'APT::Get::Assume-Yes "true";\\n' > /etc/apt/apt.conf.d/99-silicium-ci`
        : `dnf install -y sudo curl ca-certificates
printf '\\nassumeyes=True\\n' >> /etc/dnf/dnf.conf`;
      const query = isApt
        ? `dpkg-query -W -f='\${Version}' silicium-node`
        : `rpm -q --qf '%{VERSION}' silicium-node`;
      const list = isApt ? 'dpkg -L silicium-node' : 'rpm -ql silicium-node';
      const before =
        mode === 'upgrade'
          ? `bash /checks/previous-${manager}-setup.sh
bash /checks/previous-${manager}-install.sh
test "$(${query})" = "$PREVIOUS_VERSION"`
          : '';
      const command = `${setup}
${before}
mkdir -p /root/.local/share/network.silicium.node
printf preserved > /root/.local/share/network.silicium.node/upgrade-fixture
bash /checks/current-${manager}-setup.sh
bash /checks/current-${manager}-${mode === 'upgrade' ? 'update' : 'install'}.sh
bash /checks/current-${manager}-diagnose.sh
test "$(${query})" = "$EXPECTED_VERSION"
test -x /usr/bin/silicium-node
${list} | grep -E '/Network/bin/p2p_node$'
${list} | grep -E '/Network/bin/compute_daemon$'
${list} | grep -E '/Network/bin/raytracer/silicium-raytracer$'
! ldd /usr/bin/silicium-node | grep 'not found'
test "$(cat /root/.local/share/network.silicium.node/upgrade-fixture)" = preserved
${isApt ? 'dpkg --verify silicium-node' : 'rpm -V silicium-node'}`;
      const expected = packageVersions(identity.version)[isApt ? 'deb' : 'rpm'];
      const old = previousVersion ? packageVersions(previousVersion)[isApt ? 'deb' : 'rpm'] : '';
      const result = run(
        [
          'docker',
          'run',
          '--rm',
          '--network',
          network,
          '--mount',
          `type=bind,src=${checks},dst=/checks,readonly`,
          '-e',
          'DEBIAN_FRONTEND=noninteractive',
          '-e',
          `EXPECTED_VERSION=${expected}`,
          '-e',
          `PREVIOUS_VERSION=${old}`,
          image,
          'bash',
          '-euc',
          command,
        ],
        { timeout: 900_000, allowFailure: true },
      );
      process.stdout.write(result.stdout);
      process.stderr.write(result.stderr);
      if (result.status)
        throw new Failure(`Installation ${mode} failed for ${image.split('@')[0]}`);
      console.log(`ok ${++count} - ${image.split('@')[0]} ${mode}`);
    }
  writeJson(resolve(root, '.artifacts/publish/installations.json'), {
    schema_version: 1,
    source_sha: identity.source_sha,
    release_id: identity.release_id,
    tests_executed: count,
    upgrade: previous ? 'qualified' : 'not_applicable_first_candidate',
    transport: 'HTTP only in disposable fixture; signed metadata and packages unchanged',
  });
  console.log(`1..${count}\n# tests ${count}\n# pass ${count}`);
} finally {
  run(['docker', 'rm', '-f', http], { allowFailure: true });
  run(['docker', 'network', 'rm', network], { allowFailure: true });
}
