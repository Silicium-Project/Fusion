import { describe, expect, it } from 'vitest';
import { spawnSync } from 'node:child_process';
import { PACKAGE_BASES, repositoryCommands, type PackageChannel, type PackageManager } from '../utils/packageRepositories';

describe('package repository onboarding', () => {
  for (const manager of ['apt', 'dnf'] as PackageManager[]) {
    for (const channel of ['prod', 'dev'] as PackageChannel[]) {
      it(manager + '/' + channel + ' supplies valid shell with a channel-specific repository before install', () => {
        const commands = repositoryCommands(manager, channel);
        expect(commands.setup).toContain(PACKAGE_BASES[channel]);
        expect(commands.setup).toContain('silicium-' + channel + (manager === 'apt' ? '.sources' : '.repo'));
        expect(commands.install).toContain('sudo ' + manager + ' install silicium-node');
        expect(commands.setup + commands.install).not.toMatch(/install \.\//);
        expect(commands.setup).not.toMatch(/--insecure|curl -k|\.ssh/);
        for (const command of Object.values(commands)) {
          const syntax = spawnSync('bash', ['-n'], { input: command, encoding: 'utf8' });
          expect(syntax.stderr).toBe('');
          expect(syntax.status).toBe(0);
        }
      });
    }
  }
  it('uses the APT Signed-By path published by the VPS for each channel', () => {
    expect(repositoryCommands('apt', 'prod').setup).toContain('/etc/apt/keyrings/silicium-prod.gpg');
    expect(repositoryCommands('apt', 'dev').setup).toContain('/etc/apt/keyrings/silicium-dev.gpg');
  });
  it('uses the distribution-specific trust store for the dev certificate', () => {
    expect(repositoryCommands('apt', 'dev').ca).toContain('/usr/local/share/ca-certificates/');
    expect(repositoryCommands('apt', 'dev').ca).toContain('update-ca-certificates');
    expect(repositoryCommands('dnf', 'dev').ca).toContain('/etc/pki/ca-trust/source/anchors/');
    expect(repositoryCommands('dnf', 'dev').ca).toContain('update-ca-trust');
  });
});
