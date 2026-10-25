<template><div /></template>

<script setup lang="ts">
definePageMeta({ layout: 'public' });
const route = useRoute();
const platform = String(route.params.platform);
if (!['windows', 'windows-dev', 'linux-dev'].includes(platform)) {
  throw createError({ statusCode: 404, statusMessage: 'Not found' });
}
await navigateTo(
  {
    path: '/download',
    query: {
      platform: platform.startsWith('windows') ? 'windows' : 'linux',
      channel: platform === 'windows' ? 'prod' : 'dev',
    },
  },
  { redirectCode: 301, replace: true },
);
</script>
