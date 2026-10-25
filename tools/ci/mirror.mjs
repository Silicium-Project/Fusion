/** Deterministic Epitech snapshot. Never force-push, build, or mirror an unqualified ref. */
import { existsSync, readFileSync, mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { tmpdir } from 'node:os';
import { pathToFileURL } from 'node:url';
import { root, run, Failure, writeJson } from '../lib/process.mjs';
import { verifiedRun } from '../lib/github.mjs';

export function updateSnapshot(source, destination, sha, qualificationRun) {
  if (!/^[a-f0-9]{40}$/.test(sha) || !/^[1-9][0-9]*$/.test(String(qualificationRun)))
    throw new Failure('Exact source SHA and qualification run required', 2);
  const git = (...args) => run(['git', ...args], { cwd: destination }).stdout.trim();
  const sourceGit = (...args) => run(['git', ...args], { cwd: source }).stdout.trim();
  const tree = sourceGit('rev-parse', `${sha}^{tree}`);
  const metadataPath = resolve(destination, '.silicium-mirror.json');
  if (existsSync(metadataPath)) {
    const old = JSON.parse(readFileSync(metadataPath, 'utf8'));
    if (old.source_sha === sha) {
      if (git('rev-parse', 'HEAD:fusion') !== tree)
        throw new Failure('Existing mirror metadata does not match its content');
      return { status: 'unchanged', source_sha: sha, source_tree: tree };
    }
    if (
      !/^[a-f0-9]{40}$/.test(old.source_sha ?? '') ||
      run(['git', 'merge-base', '--is-ancestor', old.source_sha, sha], {
        cwd: source,
        allowFailure: true,
      }).status
    )
      throw new Failure('Mirror would move backwards or cross unrelated source history');
  }
  git('fetch', '--no-tags', source, sha);
  git('rm', '-r', '-f', '--ignore-unmatch', '--', 'fusion');
  git('read-tree', '--prefix=fusion/', '-u', sha);
  const value = {
    schema_version: 1,
    source_repository: 'Silicium-Project/Fusion',
    source_sha: sha,
    source_tree: tree,
    qualification_run: Number(qualificationRun),
  };
  writeJson(metadataPath, value);
  git('add', '--', '.silicium-mirror.json');
  if (git('rev-parse', `${git('write-tree')}:fusion`) !== tree)
    throw new Failure('Mirror tree differs from the exact Fusion commit');
  git(
    '-c',
    'user.name=Silicium Mirror',
    '-c',
    'user.email=mirror@silicium.network',
    'commit',
    '-m',
    `mirror: Fusion ${sha}`,
  );
  return { status: 'updated', ...value, mirror_sha: git('rev-parse', 'HEAD') };
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const qualified = verifiedRun(process.env.QUALIFICATION_RUN);
  if (!process.env.MIRROR_SSH_KEY || !process.env.MIRROR_KNOWN_HOSTS)
    throw new Failure('Protected Epitech deploy key and pinned SSH hosts required', 3);
  const temp = mkdtempSync(join(tmpdir(), 'silicium-mirror-'));
  try {
    const key = join(temp, 'key'),
      known = join(temp, 'known_hosts'),
      wrapper = join(temp, 'ssh'),
      destination = join(temp, 'epitech');
    writeFileSync(key, process.env.MIRROR_SSH_KEY, { mode: 0o600 });
    writeFileSync(known, process.env.MIRROR_KNOWN_HOSTS, { mode: 0o600 });
    writeFileSync(
      wrapper,
      '#!/bin/sh\nexec ssh -i "$SILICIUM_MIRROR_KEY" -o "UserKnownHostsFile=$SILICIUM_MIRROR_HOSTS" -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o BatchMode=yes -o ConnectTimeout=15 "$@"\n',
      { mode: 0o700 },
    );
    const env = {
      GIT_SSH: wrapper,
      SILICIUM_MIRROR_KEY: key,
      SILICIUM_MIRROR_HOSTS: known,
      GIT_TERMINAL_PROMPT: '0',
    };
    run(
      [
        'git',
        'clone',
        '--no-tags',
        '--single-branch',
        '--branch',
        'main',
        'git@github.com:EpitechPromo2027/G-EIP-600-lil-6-1-eip-luis.fernandes.git',
        destination,
      ],
      { env, timeout: 120_000 },
    );
    const result = updateSnapshot(root, destination, qualified.head_sha, qualified.id);
    if (result.status === 'updated')
      run(['git', 'push', 'origin', 'HEAD:main'], { cwd: destination, env, timeout: 120_000 });
    console.log(JSON.stringify({ schema_version: 1, ...result }));
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
}
