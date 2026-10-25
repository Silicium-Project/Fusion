/** Shared by the download page and installation qualification. */
import definition from './repositories.json' with { type: 'json' };
export const PACKAGE_BASES = Object.freeze(definition.origins);
export function repositoryCommands(manager, channel, { baseURL, testTransport = false } = {}) {
  if (!['apt', 'dnf'].includes(manager) || !['dev', 'prod'].includes(channel))
    throw new Error('Unknown package manager or channel');
  const base = (baseURL ?? PACKAGE_BASES[channel]).replace(/\/$/, '');
  const url = new URL(base);
  if (
    (url.protocol !== 'https:' && !(testTransport && url.protocol === 'http:')) ||
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    !/^https?:\/\/[A-Za-z0-9.:[\]-]+\/[A-Za-z0-9._/-]*$/.test(base)
  )
    throw new Error('Invalid repository origin');
  const values = { base, prefix: `silicium-${channel}` };
  return Object.fromEntries(
    Object.entries(definition.commands[manager]).map(([name, lines]) => [
      name,
      lines.map((line) => line.replace(/\{(base|prefix)\}/g, (_, key) => values[key])).join('\n'),
    ]),
  );
}
