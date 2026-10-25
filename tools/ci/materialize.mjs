/** Fetch only declared private pins, with distinct read-only keys removed before execution. */
import { existsSync, mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';
import { root, run, readJson, Failure } from '../lib/process.mjs';
import {
  workspaceConfig,
  workspaceLock,
  validateWorkspace,
  workspaceStatus,
} from '../lib/workspace.mjs';
const config = workspaceConfig(),
  lock = validateWorkspace(config, workspaceLock());
if (
  process.env.GITHUB_ACTIONS !== 'true' ||
  process.env.GITHUB_REPOSITORY !== config.integration_repository ||
  process.env.GITHUB_REF !== 'refs/heads/main' ||
  process.env.SILICIUM_SOURCE_VISIBILITY !== 'private'
)
  throw new Failure('Source keys are restricted to private Integration main', 3);
const before = workspaceStatus();
if (
  before.status !== 'success' ||
  before.components.some((component) => component.state !== 'absent')
)
  throw new Failure('Materialize only into a clean checkout with no component sources', 3);
const temporary = mkdtempSync(resolve(tmpdir(), 'silicium-source-keys-'));
try {
  const hosts = resolve(temporary, 'known_hosts');
  writeFileSync(
    hosts,
    readJson(resolve(root, 'tools/config/github-ssh.json'))
      .keys.map((key) => `github.com ${key}`)
      .join('\n') + '\n',
    { mode: 0o600 },
  );
  const wrapper = resolve(temporary, 'ssh');
  writeFileSync(
    wrapper,
    '#!/bin/sh\nexec ssh -i "$SILICIUM_COMPONENT_KEY" -o "UserKnownHostsFile=$SILICIUM_COMPONENT_HOSTS" -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o BatchMode=yes -o ConnectTimeout=15 "$@"\n',
    { mode: 0o700 },
  );
  for (const [id, component] of Object.entries(config.components)) {
    const variable = `SOURCE_KEY_${id.toUpperCase()}`;
    const secret = process.env[variable];
    if (!secret) throw new Failure(`Missing read-only source credential: ${id}`, 3);
    const key = resolve(temporary, `${id}.key`);
    writeFileSync(key, secret, { mode: 0o600 });
    delete process.env[variable];
    const path = resolve(root, component.path);
    const env = {
      GIT_SSH: wrapper,
      SILICIUM_COMPONENT_KEY: key,
      SILICIUM_COMPONENT_HOSTS: hosts,
      GIT_TERMINAL_PROMPT: '0',
    };
    run(
      [
        'git',
        'clone',
        '--no-checkout',
        '--no-tags',
        `git@github.com:${component.repository}.git`,
        path,
      ],
      { env, timeout: 120_000 },
    );
    run(['git', '-C', path, 'fetch', '--no-tags', 'origin', lock.components[id].commit], {
      env,
      timeout: 120_000,
    });
    run(['git', '-C', path, 'checkout', '--detach', lock.components[id].commit], { env });
    // Keys and Git authentication configuration are absent before any application command.
    rmSync(key);
    run([
      'git',
      '-C',
      path,
      'remote',
      'set-url',
      'origin',
      `https://github.com/${component.repository}.git`,
    ]);
    if (
      existsSync(resolve(path, '.git/config')) &&
      run(['git', '-C', path, 'config', '--get-regexp', 'core.sshCommand|http.*extraheader'], {
        allowFailure: true,
      }).status === 0
    )
      throw new Failure('Unexpected persisted source credential', 3);
  }
} finally {
  for (const id of Object.keys(config.components))
    delete process.env[`SOURCE_KEY_${id.toUpperCase()}`];
  rmSync(temporary, { recursive: true, force: true });
}
const status = workspaceStatus({ materialized: true });
if (status.status !== 'success')
  throw new Failure('The fetched composition does not match its pins', 3);
console.log(JSON.stringify(status));
