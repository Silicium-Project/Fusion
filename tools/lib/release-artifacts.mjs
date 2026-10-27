import { Failure } from './process.mjs';

const buildArtifacts = Object.freeze({
  api: 'api-binary',
  web: 'web-output',
  network: 'network-binaries',
  node: 'node-ui-output',
});

function validAttempt(attempt) {
  const value = Number(attempt);
  if (!Number.isSafeInteger(value) || value < 1)
    throw new Failure('A positive workflow attempt is required');
  return value;
}

export function releaseArtifactName(base, attempt) {
  const value = validAttempt(attempt);
  if (!/^[A-Za-z0-9][A-Za-z0-9-]{0,63}$/.test(base ?? ''))
    throw new Failure('Invalid release artifact name');
  return `${base}-${value}`;
}

export function qualifiedBuildArtifacts(attempt) {
  const value = validAttempt(attempt);
  return Object.fromEntries(
    Object.entries(buildArtifacts).map(([component, base]) => [component, `${base}-${value}`]),
  );
}

export function isQualifiedArtifactFromAttempt(name, attempt) {
  const value = validAttempt(attempt);
  const exact = new Set([
    `qualification-plan-${value}`,
    ...Object.values(buildArtifacts).map((base) => `${base}-${value}`),
  ]);
  return exact.has(name) || (name.startsWith('report-') && name.endsWith(`-${value}`));
}
