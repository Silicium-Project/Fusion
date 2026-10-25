export default defineEventHandler((event) => {
  const config = useRuntimeConfig(event).public;
  setHeader(event, 'Cache-Control', 'no-store');
  return {
    release_channel: config.releaseChannel,
    release_version: config.releaseVersion,
    release_build: config.releaseBuild,
    release_id: config.releaseId,
    manifest_digest: config.manifestDigest,
  };
});
