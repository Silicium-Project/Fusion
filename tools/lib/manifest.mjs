/** Delivery identities are immutable; a digest is never a mutable image tag. */
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { Failure } from './process.mjs';
export const sha256 = (bytes) => createHash('sha256').update(bytes).digest('hex');
export function validateManifest(m) {
  const errors = [];
  if (m.schema_version !== 1) errors.push('unsupported manifest version');
  if (!/^[a-f0-9]{40}$/.test(m.source_sha ?? '')) errors.push('invalid source SHA');
  if (!['dev', 'prod'].includes(m.channel)) errors.push('invalid channel');
  if (!/^\d+\.\d+\.\d+(?:-dev\.\d+)?$/.test(m.version ?? ''))
    errors.push('invalid release version');
  if (m.channel === 'prod' && m.version?.includes('-'))
    errors.push('production cannot use a prerelease');
  if (m.channel === 'dev' && !m.version?.includes('-dev.'))
    errors.push('development must use a prerelease');
  if (m.release_id !== `${m.channel}-${m.version}-${m.source_sha?.slice(0, 12)}`)
    errors.push('candidate identity mismatch');
  if (
    !m.qualification ||
    m.qualification.source_sha !== m.source_sha ||
    m.qualification.status !== 'success' ||
    !/^[1-9][0-9]*$/.test(String(m.qualification.run_id))
  )
    errors.push('qualification missing or stale');
  for (const component of ['api', 'web', 'network', 'node'])
    if (!m.components?.[component]) errors.push(`missing component ${component}`);
  for (const [name, c] of Object.entries(m.components ?? {})) {
    if (!['web', 'api', 'network', 'node', 'solana', 'sdk'].includes(name))
      errors.push('unknown component');
    if (!/^[a-f0-9]{40}$/.test(c.source_sha ?? ''))
      errors.push(`${name}: missing component provenance`);
    if (c.image && !/^ghcr\.io\/silicium-project\/[a-z0-9._/-]+@sha256:[a-f0-9]{64}$/.test(c.image))
      errors.push(`${name}: image must use an allowed immutable digest`);
  }
  const names = new Set();
  for (const asset of m.assets ?? []) {
    if (names.has(asset.name)) errors.push('duplicate asset');
    names.add(asset.name);
    if (
      !/^[a-zA-Z0-9][a-zA-Z0-9._-]*$/.test(asset.name ?? '') ||
      !/^[a-f0-9]{64}$/.test(asset.sha256 ?? '') ||
      !Number.isSafeInteger(asset.size) ||
      asset.size < 1
    )
      errors.push('invalid asset identity');
  }
  if (
    !['packages.tar.gz', 'deployment.tar.gz', 'qualification.json'].every((name) => names.has(name))
  )
    errors.push('incomplete candidate assets');
  return errors;
}
export function requireManifest(m) {
  const errors = validateManifest(m);
  if (errors.length) throw new Failure(errors.join('\n'), 2);
  return m;
}
export function packageVersions(version) {
  if (!/^\d+\.\d+\.\d+(?:-dev\.\d+)?$/.test(version)) throw new Failure('Invalid version', 2);
  const [base, pre] = version.split('-');
  const sequence = pre ? Number(pre.split('.')[1]) : 65535;
  if (base.split('.').some((n) => Number(n) > 65535))
    throw new Failure('Windows version fields must fit 0..65535', 2);
  if (!Number.isInteger(sequence) || sequence < 1 || sequence > (pre ? 65534 : 65535))
    throw new Failure('Windows dev sequence must fit 1..65534; 65535 is reserved for stable', 2);
  return {
    semver: version,
    deb: pre ? `${base}~${pre}` : base,
    rpm: pre ? `${base}~${pre}` : base,
    rpm_release: '1',
    windows: `${base}.${sequence}`,
  };
}
export function compareVersions(a, b) {
  packageVersions(a);
  packageVersions(b);
  const parts = (value) => {
    const [base, pre] = value.split('-');
    return [...base.split('.').map(Number), pre ? Number(pre.split('.')[1]) : 65535];
  };
  const left = parts(a),
    right = parts(b);
  for (let index = 0; index < left.length; index++)
    if (left[index] !== right[index]) return Math.sign(left[index] - right[index]);
  return 0;
}
