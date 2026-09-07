<template>
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <template v-if="name === 'overview'"><rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="4" rx="2"/><rect x="14" y="11" width="7" height="10" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/></template>
    <template v-else-if="name === 'jobs'"><path d="M8 4h8"/><path d="M9 3h6v3H9z"/><rect x="5" y="5" width="14" height="16" rx="2"/><path d="m8 11 1.5 1.5L12 10M8 16h8"/></template>
    <template v-else-if="name === 'network'"><circle cx="12" cy="5" r="2.5"/><circle cx="5" cy="18" r="2.5"/><circle cx="19" cy="18" r="2.5"/><path d="m10.8 7.2-4.6 8.6m7-8.6 4.6 8.6M7.5 18h9"/></template>
    <template v-else-if="name === 'nodes'"><rect x="3" y="4" width="7" height="7" rx="2"/><rect x="14" y="4" width="7" height="7" rx="2"/><rect x="8.5" y="15" width="7" height="6" rx="2"/><path d="M6.5 11v2h11v-2M12 13v2"/></template>
    <template v-else-if="name === 'account'"><circle cx="12" cy="8" r="3.5"/><path d="M5 21c.5-4 3-6 7-6s6.5 2 7 6"/></template>
    <template v-else-if="name === 'plus'"><path d="M12 5v14M5 12h14"/></template>
    <template v-else-if="name === 'arrow'"><path d="M5 12h14m-5-5 5 5-5 5"/></template>
    <template v-else-if="name === 'chevron'"><path d="m9 6 6 6-6 6"/></template>
    <template v-else-if="name === 'refresh'"><path d="M20 7v5h-5M4 17v-5h5"/><path d="M18.5 9A7 7 0 0 0 6 6.5L4 9m2 6a7 7 0 0 0 12 2.5L20 15"/></template>
    <template v-else-if="name === 'play'"><path d="m8 5 11 7-11 7V5Z" fill="currentColor" stroke="none"/></template>
    <template v-else-if="name === 'pause'"><path d="M8 5h3v14H8zM13 5h3v14h-3z" fill="currentColor" stroke="none"/></template>
    <template v-else-if="name === 'activity'"><path d="M3 12h4l2-7 4 14 2-7h6"/></template>
    <template v-else-if="name === 'check'"><path d="m5 12 4 4L19 6"/></template>
    <template v-else-if="name === 'clock'"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></template>
    <template v-else-if="name === 'alert'"><path d="M10.3 4.1 2.7 17.2A2 2 0 0 0 4.4 20h15.2a2 2 0 0 0 1.7-2.8L13.7 4.1a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4m0 3h.01"/></template>
    <template v-else-if="name === 'x'"><path d="m6 6 12 12M18 6 6 18"/></template>
    <template v-else-if="name === 'cube'"><path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Z"/><path d="m4.5 7.8 7.5 4.3 7.5-4.3M12 12v9"/></template>
    <template v-else-if="name === 'layers'"><path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5m-18 4 9 5 9-5"/></template>
    <template v-else-if="name === 'shield'"><path d="M12 3 5 6v5c0 4.6 2.8 8 7 10 4.2-2 7-5.4 7-10V6l-7-3Z"/><path d="m9 12 2 2 4-4"/></template>
    <template v-else-if="name === 'download'"><path d="M12 3v12m-5-5 5 5 5-5M5 21h14"/></template>
    <template v-else-if="name === 'wallet'"><path d="M4 6h14a2 2 0 0 1 2 2v11H5a2 2 0 0 1-2-2V6a3 3 0 0 1 3-3h11v3"/><path d="M15 12h5v4h-5a2 2 0 0 1 0-4Z"/></template>
    <template v-else-if="name === 'menu'"><path d="M4 7h16M4 12h16M4 17h16"/></template>
    <template v-else-if="name === 'logout'"><path d="M10 4H5v16h5m4-4 4-4-4-4m4 4H9"/></template>
    <template v-else-if="name === 'search'"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></template>
    <template v-else-if="name === 'external'"><path d="M14 4h6v6m0-6-9 9"/><path d="M19 13v6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h6"/></template>
    <template v-else-if="name === 'database'"><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/></template>
    <template v-else-if="name === 'processor'"><rect x="6" y="6" width="12" height="12" rx="2"/><rect x="9" y="9" width="6" height="6" rx="1"/><path d="M9 2v4m6-4v4M9 18v4m6-4v4M2 9h4m-4 6h4m12-6h4m-4 6h4"/></template>
    <template v-else-if="name === 'code'"><path d="m8 8-4 4 4 4m8-8 4 4-4 4m-2-11-4 14"/></template>
    <template v-else-if="name === 'result'"><path d="M5 3h10l4 4v14H5V3Z"/><path d="M14 3v5h5m-10 5 2 2 4-4"/></template>
    <template v-else-if="name === 'upload'"><path d="M12 16V4m-5 5 5-5 5 5M5 20h14"/></template>
    <template v-else-if="name === 'windows'"><path d="M3 5.1 10.4 4v7H3V5.1Zm8.6-1.3L21 2.5V11h-9.4V3.8ZM3 13h7.4v7L3 18.9V13Zm8.6 0H21v8.5l-9.4-1.3V13Z" fill="currentColor" stroke="none"/></template>
    <template v-else-if="name === 'linux'"><path d="M12.2 2.7c-2.9 0-4.8 2.7-4.8 6.2 0 1.2-.4 2.2-1 3.3-.8 1.3-1.7 2.9-.9 4.5.6 1.1 1.9 1.3 3.2 1.1.7.8 1.7 1.3 3.4 1.3 1.6 0 2.6-.5 3.3-1.3 1.3.2 2.7 0 3.2-1.1.8-1.6-.2-3.2-.9-4.5-.6-1.1-1-2.1-1-3.3 0-3.5-1.6-6.2-4.5-6.2Z" fill="currentColor" stroke="none"/><circle cx="10" cy="9.5" r=".75" fill="var(--surface)" stroke="none"/><circle cx="14" cy="9.5" r=".75" fill="var(--surface)" stroke="none"/><path d="m10.5 13 1.5 1 1.5-1" fill="none" stroke="var(--surface)" stroke-width="1.2"/><path d="M8.5 18.4 6.8 21m7-2.6 1.7 2.6" fill="none" stroke="currentColor" stroke-width="1.4"/></template>
    <template v-else><circle cx="12" cy="12" r="9"/><path d="M12 8v4m0 4h.01"/></template>
  </svg>
</template>

<script setup lang="ts">
defineProps<{ name: string }>();
</script>
