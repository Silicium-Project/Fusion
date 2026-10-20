export type PackageChannel = 'prod' | 'dev';
export type PackageManager = 'apt' | 'dnf';

export const PACKAGE_BASES: Record<PackageChannel, string> = {
  prod: 'https://vps-910c1dbc.vps.ovh.net/downloads',
  dev: 'https://10.77.0.1:8443/downloads',
};

/** These paths match the files emitted by publish-package-repositories.sh. */
export function repositoryCommands(manager: PackageManager, channel: PackageChannel) {
  const base = PACKAGE_BASES[channel];
  const prefix = 'silicium-' + channel;
  if (manager === 'apt') {
    return {
      setup: [
        'sudo install -d -m 0755 /etc/apt/keyrings',
        'curl -fsSL ' + base + '/apt/silicium-packages.asc \\',
        '  | sudo gpg --dearmor --yes -o /etc/apt/keyrings/' + prefix + '.gpg',
        'curl -fsSL ' + base + '/apt/silicium.sources \\',
        '  | sudo tee /etc/apt/sources.list.d/' + prefix + '.sources >/dev/null',
      ].join('\n'),
      install: 'sudo apt update\nsudo apt install silicium-node',
      update: 'sudo apt update\nsudo apt install --only-upgrade silicium-node',
      diagnose: 'apt-cache policy silicium-node',
      ca: [
        'sudo install -D -m 0644 ./silicium-dev-ca.crt.pem \\',
        '  /usr/local/share/ca-certificates/silicium-dev-ca.crt',
        'sudo update-ca-certificates',
      ].join('\n'),
    };
  }
  return {
    setup: [
      'sudo install -d -m 0755 /etc/yum.repos.d',
      'sudo curl -fsSL ' + base + '/rpm/silicium-node.repo \\',
      '  -o /etc/yum.repos.d/' + prefix + '.repo',
    ].join('\n'),
    install: 'sudo dnf makecache\nsudo dnf install silicium-node',
    update: 'sudo dnf upgrade silicium-node',
    diagnose: 'dnf repolist --enabled\ndnf repoquery --repo=' + prefix + ' silicium-node',
    ca: [
      'sudo install -D -m 0644 ./silicium-dev-ca.crt.pem \\',
      '  /etc/pki/ca-trust/source/anchors/silicium-dev-ca.crt',
      'sudo update-ca-trust',
    ].join('\n'),
  };
}
