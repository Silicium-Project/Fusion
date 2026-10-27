import { Failure } from './process.mjs';

export function sourcesForSuite(suiteId, config, suites) {
  if (suiteId === 'release') return Object.keys(config.components);
  const suite = suites[suiteId];
  const sources = [...new Set(suite?.sources ?? [])];
  if (!suite || !sources.length || sources.some((id) => !config.components[id]))
    throw new Failure('A registered suite with declared private sources is required', 3);
  return sources;
}
