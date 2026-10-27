import { Failure } from './process.mjs';
import { compareVersions } from './manifest.mjs';

function releaseVersion(tag, channel) {
  const patterns =
    channel === 'dev'
      ? [
          /^dev-(\d+\.\d+\.\d+-dev\.\d+)-[a-f0-9]{12}$/,
          /^v?(\d+\.\d+\.\d+-dev\.\d+)(?:-[a-f0-9]{12})?$/,
        ]
      : [/^prod-(\d+\.\d+\.\d+)-[a-f0-9]{12}$/, /^v?(\d+\.\d+\.\d+)$/];
  return patterns.map((pattern) => tag.match(pattern)?.[1]).find(Boolean) ?? null;
}

/** Require the newest published release in a channel to be the signed baseline. */
export function trustedReleaseBaseline(releases, channel) {
  if (!Array.isArray(releases) || !['dev', 'prod'].includes(channel))
    throw new Failure('A complete release list and explicit channel are required');
  if (
    releases.some(
      (release) =>
        !release ||
        typeof release.draft !== 'boolean' ||
        typeof release.prerelease !== 'boolean' ||
        !Array.isArray(release.assets),
    )
  )
    throw new Failure('The published release inventory is incomplete');

  const channelReleases = releases
    .filter((release) => !release.draft && release.prerelease === (channel === 'dev'))
    .map((release) => {
      const version = releaseVersion(release.tag_name ?? '', channel);
      if (!version)
        throw new Failure(`A published ${channel} release uses an unsupported version tag`);
      return { release, version };
    });

  const versions = new Set(channelReleases.map(({ version }) => version));
  if (versions.size !== channelReleases.length)
    throw new Failure(`Published ${channel} releases contain duplicate versions`);

  const highestPublished = channelReleases.reduce(
    (highest, row) =>
      !highest || compareVersions(row.version, highest.version) > 0 ? row : highest,
    null,
  );
  if (!highestPublished) return { highestPublished: null, previous: null };

  const highestSigned = channelReleases
    .filter(
      ({ release }) =>
        release.assets.some((asset) => asset.name === 'manifest.json') &&
        release.assets.some((asset) => asset.name === 'manifest.json.asc'),
    )
    .reduce(
      (highest, row) =>
        !highest || compareVersions(row.version, highest.version) > 0 ? row : highest,
      null,
    );

  if (highestSigned?.release.tag_name !== highestPublished.release.tag_name)
    throw new Failure(
      `The newest published ${channel} release has no signed manifest; resolve the legacy baseline before creating a candidate`,
    );

  return { highestPublished, previous: highestSigned.release };
}
